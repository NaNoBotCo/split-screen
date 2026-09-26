"""doom.py — how alarmed a headline or post reads, by a weighted word list.

score = (sum of matched weights) / sqrt(word count), so one "toxic" in a six-word
headline outweighs one in a paragraph. Also: BREAKING-style openers, capitalised
shouting, and exclamation marks. The word list is the model; edit it and rerun.
"""
from __future__ import annotations

import math
import re

WEIGHTS = {
    3: [r"recall(s|ed)?", r"contaminat\w*", r"toxic\w*", r"poison\w*", r"carcinogen\w*", r"cancer\w*",
        r"deadl(y|ier|iest)", r"lethal", r"kill(s|ed|ing|er)?", r"death(s)?", r"die(s|d)?", r"dying",
        r"outbreak", r"epidemic", r"pandemic", r"catastroph\w*", r"disaster\w*", r"devastat\w*", r"horrif\w*",
        r"neurotox\w*", r"autism", r"measles", r"allergen\w*", r"banned|ban(s|ning)?", r"emergency"],
    2: [r"crisis", r"danger\w*", r"warn(s|ing|ed)?", r"alarm\w*", r"harm\w*", r"threat\w*", r"scar(e|y|ed)",
        r"fear\w*", r"shock\w*", r"crackdown", r"war on", r"declares? war", r"slash\w*", r"gutt?ed", r"eliminat\w*",
        r"obes\w*", r"diabet\w*", r"infertil\w*", r"heart disease", r"linked to", r"causes?", r"chaos",
        r"pulled from shelves", r"removed", r"poisonous", r"risk(s|y)?", r"unsafe", r"illness\w*", r"sick\w*",
        r"investigat\w*", r"lawsuit", r"fired", r"layoffs?", r"collapse\w*", r"panic\w*"],
    1: [r"fda", r"cdc", r"hhs", r"announc\w*", r"urg\w*", r"just in", r"report(s|ed)?", r"study", r"experts?",
        r"no longer", r"end(s|ing)?", r"cut(s|ting)?", r"could", r"may", r"million(s)?", r"billion(s)?"],
}
_PAT = [(w, re.compile(r"\b(" + "|".join(ps) + r")\b", re.I)) for w, ps in WEIGHTS.items()]
_OPEN = re.compile(r"^\s*(🚨|⚠️|‼️|BREAKING|JUST IN|URGENT|ALERT|NEW)\b", re.I)
_WORD = re.compile(r"[A-Za-z']+")


def score(text: str | None) -> tuple[float, list[str]]:
    if not text:
        return 0.0, []
    words = _WORD.findall(text)
    if not words:
        return 0.0, []
    total, hits = 0.0, []
    for w, pat in _PAT:
        for m in pat.finditer(text):
            total += w
            hits.append(m.group(0).lower())
    if _OPEN.search(text):
        total += 2
        hits.append("opener")
    caps = [x for x in words if len(x) >= 4 and x.isupper()]
    if len(caps) >= 2:
        total += 1
        hits.append("caps")
    total += min(text.count("!"), 3) * 0.5
    return round(total / math.sqrt(len(words)), 3), hits
