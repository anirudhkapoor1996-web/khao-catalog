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

# ── allergen map — synced VERBATIM from HoggNative/Ingredients.swift, 27 Aug 2026
# (Anirudh's decision: the robot's dictionary always mirrors the app's. The app gate
# rejects the WHOLE feed on one undeclared allergen, so a smaller list here is not
# "looser", it is a feed-killer. Imposters mirror CatalogUpdater.swift the same way.)
ALLERGEN_KEYS = {
    "dairy": {"ghee", "curd", "butter", "cheese", "milk", "cream", "paneer", "khoya",
              "malai", "yogurt", "yoghurt", "buttermilk", "mawa", "rabri", "ricotta",
              "mozzarella", "parmesan", "feta", "cream cheese", "sour cream",
              "evaporated milk", "condensed milk", "milk powder", "dahi",
              "clarified butter", "whey", "burrata", "mascarpone", "halloumi",
              "labneh", "creme fraiche", "custard", "ice cream"},
    "egg": {"egg", "eggs", "egg white", "egg yolk", "mayo", "mayonnaise", "meringue"},
    "fish": {"fish", "fish sauce", "anchovy", "anchovies", "tuna", "salmon", "pomfret",
             "surmai", "rohu", "hilsa", "mackerel", "sardine", "cod", "bombil"},
    "shellfish": {"prawns", "prawn", "shrimp", "crab", "lobster", "squid", "clams",
                  "mussels", "oyster", "calamari", "scallop", "crayfish"},
    "peanut": {"peanut", "peanuts", "groundnut", "groundnuts", "moongphali",
               "peanut butter"},
    "nuts": {"almond", "almonds", "cashew", "cashews", "kaju", "badam", "pista",
             "pistachio", "pistachios", "walnut", "walnuts", "akhrot", "hazelnut",
             "hazelnuts", "pecan", "macadamia", "brazil nut", "pine nut", "pine nuts",
             "chironji", "mixed nuts", "almond flour", "almond milk", "almond meal",
             "cashew paste", "nutella", "marzipan", "praline"},
    "gluten": {"atta", "maida", "wheat", "wheat flour", "flour", "all purpose flour",
               "refined flour", "bread", "breadcrumbs", "pav", "bun", "burger bun",
               "pita", "tortilla", "naan", "roti", "paratha", "pasta", "noodles",
               "spaghetti", "penne", "macaroni", "lasagne", "lasagna", "udon", "ramen",
               "vermicelli", "sevai", "semolina", "suji", "sooji", "rava", "barley",
               "bulgur", "couscous", "seitan", "puff pastry", "filo", "phyllo",
               "wonton wrappers", "dumpling wrappers", "spring roll sheets",
               "samosa patti", "malt", "beer",
               "soy sauce", "soya sauce", "dark soy sauce", "light soy sauce",
               "hoisin sauce"},
    "soy": {"soy", "soya", "soy sauce", "soya sauce", "dark soy sauce",
            "light soy sauce", "hoisin sauce", "tofu", "edamame", "miso", "tempeh",
            "soya chunks", "soya granules", "soy milk", "soybean"},
    "sesame": {"sesame", "sesame oil", "sesame seeds", "til", "tahini",
               "gingelly oil", "benne"},
    "mustard": {"mustard", "mustard seeds", "mustard oil", "rai", "sarson", "kasundi",
                "dijon mustard", "wholegrain mustard"},
}
DAIRY, EGG = ALLERGEN_KEYS["dairy"], ALLERGEN_KEYS["egg"]
FLESH = {"chicken", "mutton", "lamb", "pork", "beef", "bacon", "ham", "sausage", "goat",
         "duck", "turkey", "keema", "mince", "salami", "pepperoni", "chorizo",
         "prosciutto", "veal", "venison",
         "fish", "fish sauce", "tuna", "salmon", "anchovy", "anchovies", "pomfret",
         "surmai", "rohu", "hilsa", "mackerel", "sardine", "cod", "bombil",
         "prawns", "prawn", "shrimp", "crab", "lobster", "squid", "clams", "mussels",
         "oyster", "calamari", "scallop", "crayfish"}
OTHER_ANIMAL = {"honey", "gelatin", "gelatine", "lard", "tallow", "bone broth", "dashi",
                "worcestershire"}
OG = {"onion", "onions", "spring onion", "springonion", "shallot", "shallots", "garlic",
      "garlic paste", "ginger-garlic", "leek", "leeks", "chives", "scallion",
      "scallions"}
ROOT = OG | {"potato", "potatoes", "aloo", "carrot", "carrots", "radish", "mooli",
             "beetroot", "beet", "yam", "arbi", "colocasia", "suran", "ginger",
             "ginger paste", "turnip", "sweet potato", "shakarkandi", "mushroom",
             "mushrooms"}


def _keys(ings):
    return {i["key"].lower() for i in ings}


# Compounds that borrow a dairy word but contain no dairy. Without these, containment
# matching flags "coconut milk" and "peanut butter" as dairy — 52 dishes in the shipped
# catalogue, nearly all of them the vegan options. Mirrors CatalogUpdater.dairyImposters
# in the app; the two must stay in step or the feed and the gate will disagree.
DAIRY_IMPOSTERS = {
    "coconut milk", "coconutmilk", "coconut cream", "coconut butter",
    "almond milk", "almondmilk", "soy milk", "soymilk", "soya milk",
    "oat milk", "oatmilk", "rice milk", "cashew milk", "peanut butter",
    "almond butter", "cashew butter", "cocoa butter", "apple butter",
    "butter beans", "butterbeans", "butternut", "beancurd", "bean curd",
    "fermentedbeancurd", "fermented bean curd", "butterhead", "buttermilk squash",
    "shea butter", "nut butter", "milk thistle", "milkweed", "creamer",
    "cream of tartar", "creamed corn", "coconut yogurt", "soy yogurt",
}


def _hits(ings, vocab, imposters=frozenset()):
    """Does any ingredient actually contain something from `vocab`?

    ⚠️ WHOLE-WORD, NOT SUBSTRING. Two wrong versions preceded this one, and both
    directions of the error are recorded because each looks reasonable in isolation:
      • exact equality  → "melted butter" never matched "butter". 126 dishes reached
        the live feed with undeclared dairy (11 Aug 2026).
      • loose substring → "til" matched TORTILLA, "egg" matched EGGPLANT, "rai" matched
        RAISINS, "butter" matched the vocab entry "peanut butter". 442 bundled dishes
        were wrongly flagged.
    A word is the unit that carries the meaning: "melted butter" contains the WORD
    butter; "eggplant" does not contain the WORD egg. Multi-word vocabulary terms are
    matched as a contiguous run of words.
    """
    for k in _keys(ings):
        if any(imp in k for imp in imposters):
            continue
        words = re.findall(r"[a-z]+", k)
        joined = " ".join(words)
        for v in vocab:
            vw = v.split()
            if len(vw) == 1:
                if vw[0] in words:
                    return True
            elif f" {' '.join(vw)} " in f" {joined} ":
                return True
    return False


# Gluten has imposters too: rice noodles / rice paper are the staple gluten-free
# noodle, and flagging them would strip half of South-East Asia from coeliac users.
GLUTEN_IMPOSTERS = {
    "rice noodle", "rice noodles", "rice vermicelli", "rice paper", "rice flour",
    "glass noodles", "corn tortilla", "almond flour", "chickpea flour", "besan",
    "gram flour", "coconut flour", "kuttu", "singhara", "singhare", "rajgira",
    "amaranth flour", "water chestnut flour", "buckwheat flour", "corn flour",
    "cornflour", "cornstarch", "corn starch", "tapioca flour", "arrowroot",
    "sabudana", "samak", "millet flour", "ragi",
}


def _imp(allergen):
    """Only two families have imposters. 'peanut butter' IS peanut and 'almond milk'
    IS nuts — only their DAIRY-ness is false; 'rice noodles' are noodles but not wheat."""
    if allergen == "dairy":
        return DAIRY_IMPOSTERS
    if allergen == "gluten":
        return GLUTEN_IMPOSTERS
    return frozenset()


def derive_allergens(ings):
    return sorted(a for a, kk in ALLERGEN_KEYS.items() if _hits(ings, kk, _imp(a)))


def derive_flags(ings, diet):
    vegan = diet == "veg" and not (_hits(ings, DAIRY, DAIRY_IMPOSTERS) or _hits(ings, EGG)
                                   or _hits(ings, FLESH) or _hits(ings, OTHER_ANIMAL))
    noog = not _hits(ings, OG)
    jain = diet == "veg" and noog and not _hits(ings, ROOT)
    return vegan, jain, noog


# ── the safety + quality gate: the app's isSane, in Python ──────────────────────────
def is_safe(dish):
    if not dish["id"] or not dish["name"]:
        return False, "empty id/name"
    ings = dish["ingredients"]
    for allergen, kk in ALLERGEN_KEYS.items():
        if _hits(ings, kk, _imp(allergen)) and allergen not in dish["allergens"]:
            return False, f"undeclared {allergen}"           # the one bug that can hurt
    if dish["vegan"] and (_hits(ings, DAIRY, DAIRY_IMPOSTERS) or _hits(ings, EGG)
                          or _hits(ings, FLESH)):
        return False, "vegan flag contradicts ingredients"
    if dish["diet"] == "veg" and (_hits(ings, FLESH) or _hits(ings, EGG)):
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
    # ⚠️ FIXED 1 Sep 2026 — READ THIS BEFORE TOUCHING THE REGEX AGAIN.
    #
    # The line this replaces was a single unbounded alternation containing a bare
    # `g`, so `re.sub` deleted EVERY LETTER "g" anywhere in the string:
    #     Ghee -> hee     Garlic -> arlic    Ginger -> iner    Egg -> e
    #     Yoghurt -> yohurt   Sugar -> suar   Cabbage -> cabbae
    # Measured on 30 real ingredient names, 21 came out corrupted.
    #
    # 🔴 WHY IT WAS A SAFETY BUG, NOT A TYPO: `ghee` is a DAIRY ALLERGEN KEY.
    # Stored as `hee` it matches nothing, so the ingredient-level allergen
    # re-check in ShoppingListBuilder cannot see it. Anirudh, 1 Sep 2026:
    # "full word needs to exist to warn people about possible allergens etc".
    #
    # ⚠️ AND WHY THE OBVIOUS FIX IS ALSO WRONG: simply adding \b around the old
    # list still destroys "gram flour" and "Bengal gram", because `grams?` (the
    # unit) collides with `gram` (besan, chana — real Indian ingredients, and a
    # legume). So a unit only counts as a unit when a NUMBER is attached to it.
    # That distinction is the whole fix; do not collapse these three steps back
    # into one alternation.
    #
    # 1. Units, but only where a quantity is actually attached.
    n = re.sub(r"\b\d+(?:\.\d+)?\s*(?:kg|g|ml|l|tbsp|tsp|cups?|grams?)\b", " ", n)
    # 2. Any remaining bare numbers.
    n = re.sub(r"[0-9]+", " ", n)
    # 3. Words that are ALWAYS preparation and never an ingredient. Note there is
    #    deliberately no bare `g`, `kg`, `ml` or `gram` in this list.
    n = re.sub(r"\b(?:tbsp|tsp|cups?|large|small|medium|chopped|sliced|"
               r"to taste|fresh|dried)\b", " ", n)
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

    # ⚠️ REGRESSION CASES FROM THE REAL 11 Aug 2026 FAILURE. These exact dishes reached
    # the LIVE feed with undeclared dairy because matching was exact-equality: the
    # source says "melted butter", never "butter". Each of these must now be caught.
    for label, ing_name, key in [
        ("Apple cake", "Melted butter", "melted butter"),
        ("Apple pie pops", "Unsalted butter", "unsalted butter"),
        ("Arepa Pabellón", "Corn arepa filled with mozarella cheese",
         "corn arepa filled with mozarella cheese"),
        ("Aubergine couscous salad", "Oats cheese", "oats cheese"),
    ]:
        rec = {"strMeal": label, "strArea": "Test",
               "strInstructions": "Mix.", "strIngredient1": ing_name, "strMeasure1": "1"}
        dd = normalise(rec)
        assert dd is not None, f"{label}: normalise failed"
        assert "dairy" in dd["allergens"], f"{label}: '{key}' did not derive dairy"
        assert not dd["vegan"], f"{label}: marked vegan despite '{key}'"
        ok2, why2 = is_safe(dd)
        assert ok2, f"{label}: correctly-derived dish rejected ({why2})"

    # The OTHER direction: compounds that borrow a dairy word but are dairy-free must
    # NOT be flagged, or the fix strips 52 shipped dishes from the vegans who need them.
    for label, ing_name, key in [
        ("Thai curry", "Coconut milk", "coconut milk"),
        ("Satay", "Peanut butter", "peanut butter"),
        ("Bean stew", "Butter beans", "butter beans"),
        ("Mapo tofu", "Beancurd", "beancurd"),
    ]:
        rec = {"strMeal": label, "strArea": "Test", "strInstructions": "Cook.",
               "strIngredient1": ing_name, "strMeasure1": "1"}
        dd = normalise(rec)
        assert "dairy" not in dd["allergens"], f"{label}: '{key}' wrongly derived DAIRY"
        assert is_safe(dd)[0], f"{label}: dairy-free dish wrongly rejected"
    # ...but the non-dairy allergen it really carries must still be caught.
    sat = normalise({"strMeal": "Satay", "strArea": "Test", "strInstructions": "Cook.",
                     "strIngredient1": "Peanut butter", "strMeasure1": "1"})
    assert "peanut" in sat["allergens"], "peanut butter must still derive PEANUT"

    print("SELFTEST OK — derive + gate correct: 11 Aug dairy regressions caught, "
          "imposters (coconut milk / peanut butter) not misflagged")


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
