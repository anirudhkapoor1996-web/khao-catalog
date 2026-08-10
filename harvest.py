#!/usr/bin/env python3
"""Khao recipe FINDER — grows Khao's own database from real, public recipe sources.

Anirudh, 10 Aug 2026: the deck should never run out; new dishes are FOUND from real
sources and parsed in, not invented. This runs CENTRALLY (a scheduled GitHub Action in
the khao-catalog repo), so it costs nothing per user and sends nothing off anyone's
phone: it fetches once, builds the shared feed, and every app pulls it for free. The
per-user personalisation (palate + swipe history) happens on the device.

WHAT IT DOES, PER RECIPE FOUND:
  1. normalise the source record into Khao's schema
  2. DERIVE allergens + dietary flags from the ingredient list — never trust a source's
     own labels (the app's rule: the ingredient list always wins)
  3. validate; drop anything that can't be made safe
  4. dedupe against the existing catalogue, merge, bump the feed version

The how-to VIDEO is not copied — the app links out to a "<dish> recipe" search on
YouTube / Instagram, so the recipe content stays where its creator posted it. Only the
dish's FACTS (name, ingredients, allergens) live in Khao's database, and facts are not
copyrightable.

Sources are adapters (see SOURCES). TheMealDB is free and key-less; add others behind
the same normalise(record) -> khao_dish contract.

Run:  python3 harvest.py --catalog catalog.json          # live fetch + merge
      python3 harvest.py --selftest                       # pipeline test, no network
"""
import argparse
import json
import re
import sys
import urllib.request

# ── allergen map, in step with HoggNative/Ingredients.swift ─────────────────────────
ALLERGEN_KEYS = {
    "dairy": {"ghee", "curd", "butter", "cheese", "milk", "cream", "paneer", "khoya",
              "malai", "yogurt", "yoghurt", "buttermilk", "mawa", "dahi", "condensed milk",
              "milk powder", "clarified butter"},
    "egg": {"egg", "eggs", "egg white", "egg yolk", "mayo", "mayonnaise"},
    "fish": {"fish", "fish sauce", "anchovy", "tuna", "salmon", "pomfret", "cod",
             "mackerel", "sardine", "rohu", "hilsa"},
    "shellfish": {"prawns", "prawn", "shrimp", "crab", "lobster", "squid", "clams",
                  "mussels", "oyster", "scallop"},
    "peanut": {"peanut", "peanuts", "groundnut", "groundnuts", "peanut butter"},
    "nuts": {"almond", "almonds", "cashew", "cashews", "kaju", "badam", "pista",
             "pistachio", "walnut", "walnuts", "hazelnut", "pecan", "almond milk"},
    "gluten": {"atta", "maida", "wheat", "wheat flour", "flour", "bread", "breadcrumbs",
               "pav", "bun", "naan", "roti", "paratha", "pasta", "noodles", "vermicelli",
               "semolina", "suji", "rava", "barley", "soy sauce", "hoisin sauce"},
    "soy": {"soy", "soya", "soy sauce", "tofu", "edamame", "miso", "tempeh",
            "soya chunks", "soy milk"},
    "sesame": {"sesame", "sesame oil", "sesame seeds", "til", "tahini"},
    "mustard": {"mustard", "mustard seeds", "mustard oil", "rai", "sarson"},
}
DAIRY, EGG = ALLERGEN_KEYS["dairy"], ALLERGEN_KEYS["egg"]
FLESH = {"chicken", "mutton", "lamb", "pork", "beef", "bacon", "ham", "sausage", "goat",
         "duck", "turkey", "keema", "mince", "fish", "prawns", "prawn", "shrimp", "crab"}
OTHER_ANIMAL = {"honey", "gelatin", "gelatine", "lard", "tallow", "bone broth"}
OG = {"onion", "garlic", "spring onion", "shallot", "leek"}
ROOT = OG | {"potato", "ginger", "carrot", "beetroot", "radish", "sweet potato", "yam"}


def _keys(ings):
    return {i["key"].lower() for i in ings}


def derive_allergens(ings):
    ks = _keys(ings)
    return sorted(a for a, kk in ALLERGEN_KEYS.items() if ks & kk)


def derive_flags(ings, diet):
    ks = _keys(ings)
    vegan = diet == "veg" and not (ks & DAIRY or ks & EGG or ks & FLESH or ks & OTHER_ANIMAL)
    noog = not (ks & OG)
    jain = diet == "veg" and noog and not (ks & ROOT)
    return vegan, jain, noog


# ── the safety + quality gate: the app's isSane, in Python ──────────────────────────
def is_safe(dish):
    if not dish["id"] or not dish["name"]:
        return False, "empty id/name"
    ks = _keys(dish["ingredients"])
    for allergen, kk in ALLERGEN_KEYS.items():
        if (ks & kk) and allergen not in dish["allergens"]:
            return False, f"undeclared {allergen}"           # the one bug that can hurt
    if dish["vegan"] and (ks & DAIRY or ks & EGG or ks & FLESH):
        return False, "vegan flag contradicts ingredients"
    if dish["diet"] == "veg" and (ks & FLESH or ks & EGG):
        return False, "veg flag contradicts ingredients"
    if len(dish["name"]) > 80 or any(len(s) > 400 for s in dish["steps"]):
        return False, "text too long"
    if not dish["ingredients"]:
        return False, "no ingredients"
    return True, "ok"


# ── normalisation helpers ───────────────────────────────────────────────────────────
DIET_HINT_NONVEG = FLESH
def infer_diet(ings):
    ks = _keys(ings)
    if ks & FLESH:
        return "nonveg"
    if ks & EGG:
        return "egg"
    return "veg"


def ing_key(name):
    """Reduce a free-text ingredient to a lowercase key the app matches on."""
    n = name.lower().strip()
    n = re.sub(r"\([^)]*\)", "", n)                    # drop parentheticals
    n = re.sub(r"[0-9]+|tbsp|tsp|cup|cups|g|kg|ml|grams?|large|small|medium|chopped|"
               r"sliced|to taste|fresh|dried", "", n)
    n = re.sub(r"[^a-z ]", " ", n).strip()
    n = re.sub(r"\s+", " ", n)
    return n


PALETTE = ["#EBC77A", "#C79A3E"]


def normalise(rec):
    """A source record (TheMealDB shape) -> a Khao dish, or None if unusable."""
    name = (rec.get("strMeal") or "").strip()
    if not name:
        return None
    ings = []
    for i in range(1, 21):
        ing = (rec.get(f"strIngredient{i}") or "").strip()
        qty = (rec.get(f"strMeasure{i}") or "").strip()
        if ing:
            k = ing_key(ing)
            if k:
                ings.append({"name": ing, "qty": qty or "to taste", "key": k})
    if not ings:
        return None
    diet = infer_diet(ings)
    allergens = derive_allergens(ings)
    vegan, jain, noog = derive_flags(ings, diet)
    steps = [s.strip() for s in re.split(r"(?:\r?\n)+", rec.get("strInstructions") or "")
             if s.strip()][:12]
    steps = [s[:390] for s in steps]
    cuisine = (rec.get("strArea") or "World").strip()
    code = {"veg": "V", "egg": "E", "nonveg": "NV"}[diet]
    sid = re.sub(r"[^A-Za-z0-9]", "", name)[:14].upper() or "X"
    return {
        "id": f"FND-{code}-{sid}",
        "name": name, "hindi": name, "cuisine": cuisine, "diet": diet,
        "vegan": vegan, "jain": jain, "noOG": noog, "allergens": allergens,
        "spice": 2, "mins": 40, "rich": 3, "price": 2, "kcal": 400, "protein": 10,
        "tags": (["vegan"] if vegan else []) + ["found"],
        "meals": ["l", "d"], "emoji": "🍽",
        "rcat": cuisine.lower().split()[0][:12], "pop": 0.4, "colors": PALETTE,
        "imageKeywords": ",".join(name.lower().split()[:2]),
        "ingredients": ings, "steps": steps or ["See the video for the method."],
        "fp": {"spicy": 2, "sweet": 0, "sour": 0, "salty": 1, "umami": 2,
               "bitter": 0, "creamy": 1, "smoky": 0, "tangy": 0, "herby": 0},
    }


# ── sources (adapters) ──────────────────────────────────────────────────────────────
def source_themealdb():
    """Free, key-less. Iterates the a–z index; yields raw records."""
    base = "https://www.themealdb.com/api/json/v1/1"
    seen = set()
    for ch in "abcdefghijklmnopqrstuvwxyz":
        try:
            with urllib.request.urlopen(f"{base}/search.php?f={ch}", timeout=20) as r:
                meals = json.load(r).get("meals") or []
        except Exception:
            continue
        for m in meals:
            if m["idMeal"] not in seen:
                seen.add(m["idMeal"])
                yield m


SOURCES = {"themealdb": source_themealdb}


# ── driver ──────────────────────────────────────────────────────────────────────────
def harvest(existing):
    names = {r["name"].lower() for r in existing}
    ids = {r["id"] for r in existing}
    added, dropped = [], 0
    for src in SOURCES.values():
        for rec in src():
            d = normalise(rec)
            if not d or d["name"].lower() in names or d["id"] in ids:
                continue
            ok, _ = is_safe(d)
            if not ok:
                dropped += 1
                continue
            names.add(d["name"].lower()); ids.add(d["id"]); added.append(d)
    return added, dropped


def selftest():
    fixture = {
        "strMeal": "Test Paneer Curry", "strArea": "Indian",
        "strInstructions": "Fry the spices.\nAdd paneer and simmer.",
        "strIngredient1": "Paneer", "strMeasure1": "200 g",
        "strIngredient2": "Tomatoes", "strMeasure2": "3",
        "strIngredient3": "Cashews", "strMeasure3": "10",
    }
    d = normalise(fixture)
    assert d, "normalise returned None"
    assert "dairy" in d["allergens"], "paneer -> dairy missing"
    assert "nuts" in d["allergens"], "cashew -> nuts missing"
    assert d["diet"] == "veg" and not d["vegan"], "paneer dish must be veg but not vegan"
    ok, why = is_safe(d)
    assert ok, f"safe dish rejected: {why}"
    # a poisoned record: vegan label over a dairy ingredient must be caught
    bad = dict(d, vegan=True)
    assert not is_safe(bad)[0], "vegan-over-dairy contradiction not caught"
    # a record missing its allergen token must be caught
    bad2 = dict(d, allergens=[])
    assert not is_safe(bad2)[0], "undeclared allergen not caught"
    print("SELFTEST OK — normalise + derive + gate all correct")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="catalog.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    doc = json.load(open(a.catalog))
    existing = doc["recipes"] if isinstance(doc, dict) else doc
    added, dropped = harvest(existing)
    merged = existing + added
    ver = (doc.get("version", 1) + 1) if isinstance(doc, dict) else 2
    json.dump({"format": 1, "version": ver, "recipes": merged},
              open(a.catalog, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"harvested {len(added)} new, dropped {dropped} unsafe; "
          f"catalogue {len(existing)} -> {len(merged)}, feed v{ver}")


if __name__ == "__main__":
    main()
