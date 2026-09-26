"""tally.py — the numbers under the catalog. Writes data/math.json.

Sightings are rows in items (one post or article showing one picture). Pictures are
distinct files (sha1). Families are pictures within 8 bits of each other by 64-bit
perceptual hash: the same composite, recropped or recompressed.

    python tools/tally.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import optimize, stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "vision"))
import doom  # noqa: E402

START = dt.date(2023, 9, 26)
CLASSES = ["rfk_left", "rfk_right", "thing_only", "rfk_only"]


def load():
    con = sqlite3.connect(ROOT / "data" / "catalog.sqlite")
    q = """SELECT i.id, i.source, i.query, i.post_url, i.author, i.posted_at, i.text, i.headline, i.domain,
                  i.likes, i.reposts, i.replies, i.quotes, i.sha1,
                  v.klass, v.thing_label, v.thing_score, v.seam_x, v.rfk_any, v.rfk_x, g.phash
           FROM items i JOIN vision v ON v.sha1 = i.sha1 JOIN images g ON g.sha1 = i.sha1"""
    cols = ["id", "source", "query", "post_url", "author", "posted_at", "text", "headline", "domain", "likes", "reposts",
            "replies", "quotes", "sha1", "klass", "thing", "thing_score", "seam_x", "rfk_any", "rfk_x", "phash"]
    rows = [dict(zip(cols, r)) for r in con.execute(q)]
    for r in rows:
        r["date"] = dt.date.fromisoformat(r["posted_at"][:10]) if r["posted_at"] else None
        words = " ".join(x for x in (r["headline"], r["text"]) if x)
        r["doom"], r["doom_hits"] = doom.score(words)
    fetched = con.execute("SELECT count(*) FROM images").fetchone()[0]
    total_items = con.execute("SELECT count(*) FROM items").fetchone()[0]
    return [r for r in rows if r["date"] and r["date"] >= START], fetched, total_items


# ---------- intervals and tests ----------

def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def boot_ci(x, f=np.median, n=2000, seed=7):
    x = np.asarray(x, float)
    if x.size < 3:
        return None
    rng = np.random.default_rng(seed)
    b = [f(rng.choice(x, x.size)) for _ in range(n)]
    return [round(float(np.quantile(b, 0.025)), 3), round(float(np.quantile(b, 0.975)), 3)]


# ---------- families by perceptual hash ----------

def families(phashes: list[str], radius=8):
    v = np.array([int(h, 16) for h in phashes], dtype=np.uint64)
    n = len(v)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    bits = np.unpackbits(v.view(np.uint8).reshape(n, 8), axis=1) if n else np.zeros((0, 64), np.uint8)
    for i in range(n):
        d = (bits[i + 1:] != bits[i]).sum(1)
        for j in np.nonzero(d <= radius)[0]:
            ra, rb = find(i), find(i + 1 + int(j))
            if ra != rb:
                parent[rb] = ra
    return [find(i) for i in range(n)]


def powerlaw(x):
    """Discrete power-law fit (Clauset, Shalizi & Newman 2009): alpha by MLE, xmin by least KS distance."""
    x = np.asarray(sorted(x), float)
    best = None
    for xmin in sorted(set(x[x >= 1]))[:30]:
        t = x[x >= xmin]
        if t.size < 10:
            break
        a = 1 + t.size / np.sum(np.log(t / (xmin - 0.5)))
        emp = np.arange(1, t.size + 1) / t.size
        model = 1 - (t / xmin) ** (1 - a)
        ks = float(np.max(np.abs(emp - model)))
        if best is None or ks < best["ks"]:
            best = {"alpha": round(float(a), 3), "xmin": int(xmin), "ks": round(ks, 4), "n_tail": int(t.size)}
    return best


def gini(x):
    x = np.sort(np.asarray(x, float))
    if x.size == 0 or x.sum() == 0:
        return None
    n = x.size
    return round(float((2 * np.arange(1, n + 1) - n - 1) @ x / (n * x.sum())), 4)


# ---------- time ----------

def daily(rows, pred):
    days = (dt.date.today() - START).days + 1
    c = np.zeros(days, int)
    for r in rows:
        if pred(r):
            i = (r["date"] - START).days
            if 0 <= i < days:
                c[i] += 1
    return c


def pelt_poisson(y, pen=None):
    """Change points in a count series: exact PELT (Killick 2012) with a Poisson cost."""
    y = np.asarray(y, float)
    n = y.size
    pen = pen if pen is not None else 2 * math.log(max(n, 2))
    cs = np.concatenate([[0], np.cumsum(y)])

    def cost(a, b):
        s, L = cs[b] - cs[a], b - a
        return 0.0 if s == 0 else -2 * (s * math.log(s / L) - s)

    F = [-pen] + [0.0] * n
    last = [0] * (n + 1)
    R = [0]
    for t in range(1, n + 1):
        cands = [(F[s] + cost(s, t) + pen, s) for s in R]
        F[t], last[t] = min(cands)
        R = [s for (v, s) in cands if v - pen <= F[t]] + [t]
    cps, t = [], n
    while t > 0:
        cps.append(t)
        t = last[t]
    cps = sorted(cps)
    segs, a = [], 0
    for b in cps:
        segs.append({"start": (START + dt.timedelta(days=a)).isoformat(),
                     "end": (START + dt.timedelta(days=b - 1)).isoformat(),
                     "rate_per_day": round(float(y[a:b].mean()), 3)})
        a = b
    return segs


def hawkes(times_days):
    """Self-exciting fit: lambda(t) = mu + alpha * beta * sum exp(-beta (t - t_i)).
    alpha is the branching ratio: the share of sightings set off by an earlier one."""
    t = np.sort(np.asarray(times_days, float))
    if t.size < 30:
        return None
    T = t[-1] + 1e-6

    def nll(p):
        mu, a, b = np.exp(p)
        if a >= 0.999:
            return 1e12
        A, ll, prev = 0.0, 0.0, None
        for ti in t:
            if prev is not None:
                A = math.exp(-b * (ti - prev)) * (1 + A)
            ll += math.log(mu + a * b * A)
            prev = ti
        comp = mu * T + a * np.sum(1 - np.exp(-b * (T - t)))
        return -(ll - comp)

    best = None
    for g in ([math.log(t.size / T), math.log(0.5), math.log(1.0)], [math.log(t.size / T / 2), math.log(0.8), math.log(4.0)]):
        r = optimize.minimize(nll, g, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-4})
        if best is None or r.fun < best.fun:
            best = r
    mu, a, b = np.exp(best.x)
    return {"mu_per_day": round(float(mu), 4), "branching_ratio": round(float(a), 4),
            "decay_hours": round(float(24 / b), 2), "n": int(t.size)}


def rayleigh_hours(hours):
    th = np.asarray(hours, float) / 24 * 2 * math.pi
    if th.size < 10:
        return None
    C, S = np.cos(th).mean(), np.sin(th).mean()
    R = math.hypot(C, S)
    n = th.size
    z = n * R * R
    p = math.exp(math.sqrt(1 + 4 * n + 4 * (n * n - (n * R) ** 2)) - (1 + 2 * n))
    peak = (math.degrees(math.atan2(S, C)) % 360) / 15
    return {"R": round(R, 4), "z": round(z, 3), "p": float(f"{min(1, p):.3g}"), "peak_hour_utc": round(peak, 2), "n": n}


def entropy(c: Counter):
    n = sum(c.values())
    if n == 0:
        return None
    p = np.array(list(c.values()), float) / n
    H = float(-(p * np.log2(p)).sum())
    return {"bits": round(H, 3), "effective_kinds": round(2 ** H, 2), "kinds": len(c)}


def jsd(a: Counter, b: Counter):
    keys = sorted(set(a) | set(b))
    p = np.array([a[k] for k in keys], float)
    q = np.array([b[k] for k in keys], float)
    if p.sum() == 0 or q.sum() == 0:
        return None
    p, q = p / p.sum(), q / q.sum()
    m = (p + q) / 2

    def kl(x, y):
        z = x > 0
        return float((x[z] * np.log2(x[z] / y[z])).sum())
    return round((kl(p, m) + kl(q, m)) / 2, 4)


def xcorr(a, b, maxlag=14):
    a = (a - a.mean()) / (a.std() + 1e-9)
    b = (b - b.mean()) / (b.std() + 1e-9)
    out = []
    for L in range(-maxlag, maxlag + 1):
        if L >= 0:
            r = float(np.mean(a[L:] * b[:b.size - L]))
        else:
            r = float(np.mean(a[:L] * b[-L:]))
        out.append((L, round(r, 4)))
    return out


def main():
    rows, fetched, total_items = load()
    out = {"built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "window": [START.isoformat(), dt.date.today().isoformat()],
           "items_catalogued": total_items, "pictures_looked_at": fetched, "sightings_scored": len(rows)}

    # share of thing-story pictures that carry his face, and that put it on the left, month by month.
    # thing stories: outlet articles found by slug, GDELT articles, Bluesky posts found by a thing term
    NAME_Q = {"RFK", "Robert F. Kennedy", "Secretary Kennedy", "Kennedy HHS"}
    story = [r for r in rows if r["source"] in ("site", "gdelt") or (r["source"] == "bsky" and r["query"] not in NAME_Q)]
    seen_pic = {}
    for r in story:
        seen_pic.setdefault(r["sha1"], r)
    pics = list(seen_pic.values())
    n = len(pics)
    face = sum(r["klass"] in ("rfk_left", "rfk_right", "rfk_only") for r in pics)
    left = sum(r["klass"] == "rfk_left" for r in pics)
    right = sum(r["klass"] == "rfk_right" for r in pics)
    thing_alone = sum(r["klass"] == "thing_only" for r in pics)
    months = defaultdict(lambda: [0, 0, 0, 0])
    for r in pics:
        m = months[r["date"].strftime("%Y-%m")]
        m[0] += 1
        m[1] += r["klass"] in ("rfk_left", "rfk_right", "rfk_only")
        m[2] += r["klass"] == "rfk_left"
        m[3] += r["klass"] == "thing_only"
    out["thing_stories"] = {
        "pictures": n, "with_his_face": face, "rfk_left": left, "rfk_right": right, "thing_alone": thing_alone,
        "share_face": round(face / n, 4) if n else None, "share_face_ci": wilson(face, n),
        "share_left": round(left / n, 4) if n else None, "share_left_ci": wilson(left, n),
        "left_given_face_and_thing": round(left / (left + right), 4) if left + right else None,
        "thing_pictures_with_him_beside": round((left + right) / (left + right + thing_alone), 4) if left + right + thing_alone else None,
        "thing_pictures_with_him_beside_ci": wilson(left + right, left + right + thing_alone),
        "by_outlet": {},
        "monthly": {k: {"pictures": v[0], "face": v[1], "rfk_left": v[2], "thing_alone": v[3],
                        "share_left": round(v[2] / v[0], 4) if v[0] else None, "share_left_ci": wilson(v[2], v[0])}
                    for k, v in sorted(months.items())},
    }
    dom = defaultdict(lambda: [0, 0])
    for r in pics:
        d = (r["domain"] or "").removeprefix("www.")
        dom[d][0] += 1
        dom[d][1] += r["klass"] == "rfk_left"
    out["thing_stories"]["by_outlet"] = {d: {"pictures": a, "rfk_left": b, "share_left": round(b / a, 4)}
                                         for d, (a, b) in sorted(dom.items(), key=lambda t: -t[1][1]) if b and d != "bsky.app"}
    # trend in the left share: logistic slope per month by least squares on the logit of monthly shares
    xs, ys, ws = [], [], []
    for i, (k, v) in enumerate(sorted(months.items())):
        if v[0] >= 20:
            p = (v[2] + 0.5) / (v[0] + 1)
            xs.append(i)
            ys.append(math.log(p / (1 - p)))
            ws.append(v[0] * p * (1 - p))
    if len(xs) >= 4:
        W = np.diag(ws)
        X = np.column_stack([np.ones(len(xs)), xs])
        beta = np.linalg.solve(X.T @ W @ X, X.T @ W @ np.array(ys))
        cov = np.linalg.inv(X.T @ W @ X)
        out["thing_stories"]["left_logit_slope_per_month"] = {"slope": round(float(beta[1]), 4),
                                                             "se": round(float(math.sqrt(cov[1, 1])), 4),
                                                             "odds_ratio_per_year": round(float(math.exp(12 * beta[1])), 3)}

    # one account's whole feed: the denominator is every picture it posted, so month-to-month shares compare
    acct = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
    NAMES = re.compile(r"\b(RFK|Kennedy|HHS)\b")
    seen_ap = set()
    for r in rows:
        if r["query"] != "account" or (r["author"], r["sha1"]) in seen_ap:
            continue
        seen_ap.add((r["author"], r["sha1"]))
        m = acct[r["author"]][r["date"].strftime("%Y-%m")]
        m[0] += 1
        m[1] += r["klass"] == "rfk_left"
        m[2] += r["klass"] == "rfk_right"
        m[3] += r["klass"] == "thing_only"
        m[4] += r["klass"] == "rfk_left" and bool(NAMES.search(" ".join(x for x in (r["text"], r["headline"]) if x)))
    out["accounts"] = {}
    for a, months_a in acct.items():
        tot_left = sum(v[1] for v in months_a.values())
        if tot_left < 3:
            continue
        series = {k: {"pictures": v[0], "rfk_left": v[1], "rfk_right": v[2], "thing_alone": v[3],
                      "share_left": round(v[1] / v[0], 4) if v[0] else None, "share_left_ci": wilson(v[1], v[0]),
                      "left_naming_him": v[4]}
                  for k, v in sorted(months_a.items())}
        d_left = daily([r for r in rows if r["author"] == a and r["query"] == "account"], lambda r: r["klass"] == "rfk_left")
        first = next((k for k, v in sorted(months_a.items()) if v[1]), None)
        out["accounts"][a] = {"monthly": series, "first_left_month": first,
                              "change_points": pelt_poisson(d_left) if d_left.sum() >= 5 else None}

    # families over every scored picture that landed in a class
    kept = [r for r in rows if r["klass"] in CLASSES]
    pics = sorted({r["sha1"]: r["phash"] for r in kept}.items())
    fam = dict(zip([s for s, _ in pics], families([h for _, h in pics]))) if pics else {}
    for r in kept:
        r["family"] = fam.get(r["sha1"])

    by = defaultdict(list)
    for r in kept:
        by[r["klass"]].append(r)
    out["classes"] = {}
    for k in CLASSES:
        R = by[k]
        fams = Counter(r["family"] for r in R)
        out["classes"][k] = {
            "sightings": len(R), "pictures": len({r["sha1"] for r in R}), "families": len(fams),
            "by_source": dict(Counter(r["source"] for r in R)),
            "doom_mean": round(float(np.mean([r["doom"] for r in R])), 3) if R else None,
            "doom_mean_ci": boot_ci([r["doom"] for r in R], np.mean),
            "doom_share_nonzero": round(float(np.mean([r["doom"] > 0 for r in R])), 3) if R else None,
            "reuse_gini": gini(list(fams.values())),
            "reuse_powerlaw": powerlaw(list(fams.values())),
            "top_families": [{"size": n, "sha1": next(r["sha1"] for r in R if r["family"] == f)}
                             for f, n in fams.most_common(12)],
        }

    # left against right
    L, Rt = len(by["rfk_left"]), len(by["rfk_right"])
    lf = len({r["family"] for r in by["rfk_left"]})
    rf = len({r["family"] for r in by["rfk_right"]})
    side = {"sightings": {"left": L, "right": Rt}, "families": {"left": lf, "right": rf}}
    if L + Rt:
        side["share_left_sightings"] = round(L / (L + Rt), 4)
        side["share_left_ci"] = wilson(L, L + Rt)
        side["binom_p_sightings"] = float(f"{stats.binomtest(L, L + Rt, 0.5).pvalue:.3g}")
        side["beta_posterior_p_left_gt_half"] = round(float(1 - stats.beta(L + 1, Rt + 1).cdf(0.5)), 4)
    if lf + rf:
        side["share_left_families"] = round(lf / (lf + rf), 4)
        side["share_left_families_ci"] = wilson(lf, lf + rf)
        side["binom_p_families"] = float(f"{stats.binomtest(lf, lf + rf, 0.5).pvalue:.3g}")
    seams = [r["seam_x"] for r in by["rfk_left"] + by["rfk_right"] if r["seam_x"] is not None]
    if seams:
        side["seam_x_mean"] = round(float(np.mean(seams)), 4)
        side["seam_x_sd"] = round(float(np.std(seams)), 4)
    out["left_vs_right"] = side

    # what sits beside him
    mix = {k: Counter(r["thing"] for r in by[k]) for k in CLASSES}
    out["things"] = {k: dict(mix[k].most_common()) for k in CLASSES}
    out["thing_entropy"] = {k: entropy(mix[k]) for k in CLASSES}
    out["jsd_left_right_things"] = jsd(mix["rfk_left"], mix["rfk_right"])
    keys = sorted(set(mix["rfk_left"]) | set(mix["rfk_right"]))
    tab = np.array([[mix["rfk_left"][k] for k in keys], [mix["rfk_right"][k] for k in keys]])
    tab = tab[:, tab.sum(0) > 0]
    if tab.shape[1] >= 2 and tab.sum(1).min() > 0:
        chi = stats.chi2_contingency(tab)
        out["chi2_side_by_thing"] = {"chi2": round(float(chi[0]), 3), "dof": int(chi[2]), "p": float(f"{chi[1]:.3g}")}

    # monthly thing entropy for the main pattern
    months = defaultdict(Counter)
    for r in by["rfk_left"]:
        months[r["date"].strftime("%Y-%m")][r["thing"]] += 1
    out["monthly_left_entropy"] = {m: entropy(c) for m, c in sorted(months.items())}

    # doom by class: rank tests against rfk_only
    base = [r["doom"] for r in by["rfk_only"]]
    out["doom_tests"] = {}
    for k in ["rfk_left", "rfk_right", "thing_only"]:
        x = [r["doom"] for r in by[k]]
        if len(x) >= 5 and len(base) >= 5:
            u = stats.mannwhitneyu(x, base, alternative="two-sided")
            out["doom_tests"][k + "_vs_rfk_only"] = {
                "U": float(u.statistic), "p": float(f"{u.pvalue:.3g}"),
                "prob_superiority": round(float(u.statistic / (len(x) * len(base))), 4)}
    words = Counter(h for r in by["rfk_left"] + by["rfk_right"] for h in r["doom_hits"])
    out["doom_words_split"] = dict(words.most_common(25))

    # engagement (Bluesky rows carry counts)
    eng = {}
    for k in CLASSES:
        x = [(r["likes"] or 0) + (r["reposts"] or 0) + (r["quotes"] or 0) for r in by[k] if r["source"] == "bsky"]
        if x:
            eng[k] = {"n": len(x), "median": float(np.median(x)), "median_ci": boot_ci(x),
                      "mean": round(float(np.mean(x)), 2), "p99": float(np.quantile(x, 0.99))}
    out["engagement"] = eng
    groups = [[np.log1p((r["likes"] or 0) + (r["reposts"] or 0)) for r in by[k] if r["source"] == "bsky"] for k in CLASSES]
    groups = [g for g in groups if len(g) >= 5]
    if len(groups) >= 2:
        h = stats.kruskal(*groups)
        out["engagement_kruskal"] = {"H": round(float(h.statistic), 3), "p": float(f"{h.pvalue:.3g}")}
    sp = [(r["doom"], (r["likes"] or 0) + (r["reposts"] or 0)) for r in by["rfk_left"] + by["rfk_right"] if r["source"] == "bsky"]
    if len(sp) >= 10:
        rho = stats.spearmanr([a for a, _ in sp], [b for _, b in sp])
        out["doom_vs_engagement_spearman"] = {"rho": round(float(rho.statistic), 4), "p": float(f"{rho.pvalue:.3g}"), "n": len(sp)}

    # time: change points, self-excitation, hour of day, news against social
    series = {k: daily(rows, lambda r, k=k: r["klass"] == k) for k in CLASSES}
    out["daily"] = {k: v.tolist() for k, v in series.items()}
    out["change_points"] = {k: pelt_poisson(series[k]) for k in ["rfk_left", "rfk_right", "thing_only"] if series[k].sum() >= 10}
    out["hawkes"] = {}
    for k in ["rfk_left", "rfk_right", "thing_only"]:
        ts = []
        for r in by[k]:
            p = r["posted_at"]
            try:
                t = dt.datetime.fromisoformat(p.replace("Z", "+00:00"))
            except ValueError:
                continue
            ts.append((t - dt.datetime(START.year, START.month, START.day, tzinfo=dt.timezone.utc)).total_seconds() / 86400)
        out["hawkes"][k] = hawkes(ts)
    hrs = []
    for r in by["rfk_left"]:
        try:
            t = dt.datetime.fromisoformat(r["posted_at"].replace("Z", "+00:00"))
            hrs.append(t.hour + t.minute / 60)
        except ValueError:
            pass
    out["hour_of_day_rfk_left"] = rayleigh_hours(hrs)
    news = daily(rows, lambda r: r["source"] == "gdelt")
    social = daily(rows, lambda r: r["source"] == "bsky")
    if news.sum() and social.sum():
        xc = xcorr(news.astype(float), social.astype(float))
        out["news_social_xcorr"] = {"by_lag_days": xc, "peak": max(xc, key=lambda t: t[1])}
    out["rfk_face_x"] = {"left_mean": round(float(np.mean([r["rfk_x"] for r in by["rfk_left"]])), 4) if by["rfk_left"] else None,
                         "right_mean": round(float(np.mean([r["rfk_x"] for r in by["rfk_right"]])), 4) if by["rfk_right"] else None}

    (ROOT / "data" / "math.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("sightings_scored", "left_vs_right")}, indent=1))
    ts = {k: v for k, v in out["thing_stories"].items() if k not in ("monthly", "by_outlet")}
    print(json.dumps(ts, indent=1))


if __name__ == "__main__":
    main()
