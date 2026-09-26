"""things.py — what a picture (or half of one) shows, by CLIP zero-shot labels.

CLIP (a model trained on 2 billion captioned web images) scores a picture against
each written label; the scores are turned into shares that sum to 1 over every label
below. THINGS are what the posts put beside RFK Jr.; SCENE labels soak up the rest.
"""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image

THINGS = {
    "sugar": ["a bowl of white sugar", "sugar cubes", "a spoonful of sugar", "a bag of sugar"],
    "soda": ["a can of soda", "a bottle of cola", "soft drinks", "a fountain soda cup"],
    "candy": ["candy", "gummy candy", "brightly colored candy", "a chocolate bar", "lollipops"],
    "food dye": ["artificial food coloring", "red dye 40", "neon colored snacks", "colorful frosted cereal"],
    "cereal": ["breakfast cereal", "a box of cereal", "a bowl of cereal"],
    "donuts & cake": ["donuts", "a cake", "cupcakes", "cookies", "pastries"],
    "ice cream": ["ice cream", "a milkshake"],
    "chips & snacks": ["potato chips", "processed snack food", "cheese puffs", "a bag of chips"],
    "fast food": ["a fast food hamburger", "french fries", "fast food", "a McDonald's meal", "fried chicken", "pizza"],
    "processed meat": ["hot dogs", "processed meat", "bacon", "deli meat"],
    "seed oil": ["bottles of cooking oil", "seed oil", "vegetable oil", "deep fryer oil", "margarine"],
    "milk": ["a glass of milk", "raw milk", "a gallon of milk", "dairy milk bottles"],
    "infant formula": ["infant formula", "a baby bottle", "a can of baby formula"],
    "water & fluoride": ["a glass of tap water", "water from a faucet", "fluoride", "bottled water"],
    "alcohol": ["beer", "a glass of wine", "liquor bottles", "cocktails"],
    "tobacco & vapes": ["cigarettes", "a vape pen", "nicotine pouches"],
    "energy drinks": ["energy drinks", "a can of energy drink"],
    "pills & painkillers": ["pills", "a bottle of Tylenol", "acetaminophen tablets", "prescription medicine", "antidepressant pills"],
    "vaccines": ["a vaccine syringe", "vaccine vials", "a shot being given", "a needle"],
    "sweeteners": ["artificial sweetener packets", "diet soda", "aspartame"],
    "school lunch": ["a school lunch tray", "cafeteria food"],
    "plated food": ["a plate of food", "a meal on a table", "groceries", "a supermarket aisle"],
    "sunscreen & cosmetics": ["sunscreen", "cosmetics", "shampoo bottles"],
    "phones & screens": ["a smartphone", "a child looking at a screen"],
    "eggs": ["eggs", "a carton of eggs", "a hand holding an egg"],
    "produce": ["lettuce", "jalapeño peppers", "fresh herbs", "a salad", "fresh vegetables in a grocery store", "fruit"],
    "raw meat": ["ground beef", "raw meat", "packaged meat with a recall sticker", "chicken wings"],
    "germs & disease": ["bacteria under a microscope", "a virus", "a parasite", "a tick", "a skin rash",
                        "a sick child in bed", "a mosquito"],
    "pet food": ["dog food", "a puppy eating from a bowl", "pet food"],
    "chemicals": ["hazardous chemicals", "a worker in a hazmat suit", "pesticide spraying"],
}
SCENE = [
    "a portrait of a man", "a man speaking at a podium", "a man in a suit", "a politician", "a woman", "a woman in a dress",
    "a celebrity on a red carpet", "a selfie", "a family photo", "a baby", "children playing", "a doctor", "a nurse",
    "a scientist", "a crowd of people", "people at a party", "a sports team", "football players", "a concert",
    "a building", "a house", "the White House", "the US Capitol", "a courtroom", "a hospital room", "a laboratory",
    "an office", "a classroom", "a restaurant interior", "a shrine or altar", "a religious ceremony", "a street",
    "a city skyline", "a landscape", "the sky", "a forest", "the ocean", "a garden", "a lawn",
    "a screenshot of a tweet", "a screenshot of a social media post", "text on a white background", "a poll result",
    "a newspaper page", "a magazine page", "a book cover", "a movie poster", "a political campaign poster",
    "an illustration", "digital art", "neon doodles on a black background", "emoji", "a comic strip", "a cartoon",
    "a painting", "a sculpture", "a toy", "action figures", "a puppet", "a video game", "a trading card",
    "a television studio", "a news broadcast", "a computer screen", "a record player", "furniture",
    "a close-up of skin", "a hand", "a close-up of a face", "an animal", "a dog", "a cat", "a bird",
    "a horse", "a bear", "a car", "an airplane", "a gun", "money", "an American flag", "a map", "an infographic",
    "a chart or graph", "a table of numbers", "a logo", "a meme with text", "a protest sign", "a protest",
    "a document", "a podium with microphones",
]

_m = _pre = _tok = _T = None
_labels: list[tuple[str, str]] = []  # (group, prompt)
DEV = "mps" if torch.backends.mps.is_available() else "cpu"
torch.set_num_threads(2)  # several classifier shards share the cores


def _load():
    global _m, _pre, _T
    if _m is not None:
        return
    import open_clip
    _m, _, _pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    _m = _m.to(DEV).eval()
    tok = open_clip.get_tokenizer("ViT-B-32")
    for g, ps in THINGS.items():
        _labels.extend((g, p) for p in ps)
    _labels.extend(("scene", p) for p in SCENE)
    with torch.no_grad():
        t = _m.encode_text(tok([f"a photo of {p}" for _, p in _labels]).to(DEV))
        _T = t / t.norm(dim=-1, keepdim=True)


def score(imgs: list[Image.Image]) -> list[dict]:
    """Per image: group shares (sum to 1 with 'scene'), best thing cosine, top prompts."""
    _load()
    if not imgs:
        return []
    with torch.no_grad():
        x = torch.stack([_pre(im) for im in imgs]).to(DEV)
        f = _m.encode_image(x)
        f = f / f.norm(dim=-1, keepdim=True)
        sim = f @ _T.T
        p = (100.0 * sim).softmax(dim=-1).cpu().numpy()
        raw = sim.cpu().numpy()
    out = []
    groups = list(THINGS) + ["scene"]
    for row in p:
        g = {k: 0.0 for k in groups}
        for (grp, _), v in zip(_labels, row):
            g[grp] += float(v)
        top = np.argsort(-row)[:5]
        things = {k: v for k, v in g.items() if k != "scene"}
        best = max(things, key=things.get)
        cos = raw[len(out)]
        out.append({"groups": g, "best": best, "best_share": things[best],
                    "thing_mass": 1.0 - g["scene"], "thing_cos": float(max(cos[i] for i, (grp, _) in enumerate(_labels) if grp != "scene")),
                    "top": [(_labels[i][1], round(float(row[i]), 3)) for i in top]})
    return out
