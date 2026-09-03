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


# ── SINGULAR AND PLURAL ARE THE SAME INGREDIENT ────────────────────────────────────
# Anirudh's ruling, 4 Sep 2026, verbatim: "all plurals and singulars are to be treated
# the same. If an ingredient exists, an allergic / intolerant person will still be
# affected if it's one or two."
#
# Measured against live feed v11 the day it was written: the catalogue held 35
# singular/plural key pairs. Whole-word matching — the fix that ended the 442 false
# flags — is exactly what makes "tomatoes" miss the vocabulary entry "tomato", and it
# hid SEVEN real defects, including two sardine dishes flagged vegan.
#
# Mirrors `IngredientFacts.singular` in HoggNative/Ingredients.swift and
# `IngredientFacts.singular` in engine/Ingredients.kt. All three must move together.
# ⚠️ Deliberately NOT a general stemmer. -us and -ss are left alone so "hummus",
# "couscous" and "molasses" survive.
def _singular(w):
    w = w.lower()
    if len(w) <= 3 or w.endswith("ss") or w.endswith("us"):
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("oes"):
        return w[:-2]
    if w.endswith(("ches", "shes", "xes", "zes")):
        return w[:-2]
    if w.endswith("ves"):
        return w[:-3] + "f"
    if w.endswith("s"):
        return w[:-1]
    return w


# "goats cheese" is CHEESE, not goat. Found 4 Sep 2026: adding the plural pass made
# `goats` normalise to `goat`, which is in FLESH, and three vegetarian dishes were about
# to be reclassified as meat. Same shape as DAIRY_IMPOSTERS — the word is borrowed, the
# ingredient is not. Mirrors `IngredientFacts.fleshImposters` in the app.
FLESH_IMPOSTERS = {
    "goat cheese", "goats cheese", "goat's cheese", "goatcheese",
    "goat milk", "goats milk", "goat's milk", "goat curd",
    "goat butter", "goat yoghurt", "goat yogurt", "goats curd", "goat's curd",
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
        nwords = [_singular(w) for w in words]
        njoined = " ".join(nwords)
        for v in vocab:
            vw = v.split()
            if len(vw) == 1:
                if vw[0] in words:
                    return True
                if _singular(vw[0]) in nwords:            # 4 Sep 2026: singular == plural
                    return True
            else:
                if f" {' '.join(vw)} " in f" {joined} ":
                    return True
                nvw = [_singular(x) for x in vw]
                if f" {' '.join(nvw)} " in f" {njoined} ":
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
                                   or _hits(ings, FLESH, FLESH_IMPOSTERS)
                                   or _hits(ings, OTHER_ANIMAL))
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
                          or _hits(ings, FLESH, FLESH_IMPOSTERS)):
        return False, "vegan flag contradicts ingredients"
    if dish["diet"] == "veg" and (_hits(ings, FLESH, FLESH_IMPOSTERS) or _hits(ings, EGG)):
        return False, "veg flag contradicts ingredients"
    # ⚠️ ADDED 4 Sep 2026 — a HOLE THAT WAS OPEN ON BOTH PLATFORMS, independent of the
    # plural fix. The vegan check above compared INGREDIENTS, and the token check that
    # sat beside it in the app looked at dairy and egg only. So a dish could declare the
    # FISH allergen and still be flagged vegan, and two did: "Fresh sardines" was
    # allergens=["fish","gluten"], diet=veg, vegan=true, jain=true.
    _alg = set(dish.get("allergens") or [])
    if dish["vegan"] and (_alg & {"dairy", "egg", "fish", "shellfish"}):
        return False, "vegan flag contradicts its own allergen tokens"
    if dish["diet"] in ("veg", "egg") and (_alg & {"fish", "shellfish"}):
        return False, "diet contradicts its own allergen tokens"
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



# ── the one-off repair pass ─────────────────────────────────────────────────────────
#
# WHY THIS EXISTS, AND WHY `harvest` COULD NOT DO IT.
# `harvest()` does `merged = existing + added` — it APPENDS dishes it has never seen and
# carries every existing row through untouched. So fixing `ing_key` above stops FUTURE
# corruption and repairs nothing already shipped. Measured on feed v10: the old bare-`g`
# regex had corrupted 1,557 ingredient rows across 545 of 1,958 recipes, hiding an
# allergen on 25 of them — `Ghee`->`hee` (dairy), `Egg`/`Eggs`->`e`/`es`, `Groundnut
# oil`->`roundnut oil` (peanut), `Spaghetti`->`spahetti` (gluten).
#
# ⚠️ THE RULE THAT MAKES THIS SAFE: MONOTONE, ONE DIRECTION ONLY.
# An earlier version of this pass re-derived `allergens` outright. Measured, that would
# have REMOVED at least one stored allergen from 622 of 1,958 recipes — those declarations
# are curated or source-supplied and are often stricter than the ingredient list implies.
# A fix for a bug that dropped allergens must never drop more of them. So:
#   • allergens        → UNION. Keep every stored one, add what the repaired keys reveal.
#   • diet             → tighten only (veg -> egg -> nonveg). Never loosen.
#   • vegan/jain/noOG  → may be switched OFF. Never switched ON.
#   • keys             → touched ONLY where the stored key is exactly what the BROKEN
#                        ing_key produced AND the fixed one differs, so the 1,236
#                        hand-curated keys ("Chicken thigh, boneless" -> "chicken") are
#                        left alone.
# The three invariants are ASSERTED below, not promised in a comment.


def _broken_ing_key(name):
    """The exact pre-fix function, kept verbatim so the repair can recognise its output.
    Do not 'tidy' this — it is a fingerprint, not logic."""
    n = name.lower().strip()
    n = re.sub(r"\([^)]*\)", "", n)
    n = re.sub(r"[0-9]+|tbsp|tsp|cup|cups|g|kg|ml|grams?|large|small|medium|chopped|"
               r"sliced|to taste|fresh|dried", "", n)
    n = re.sub(r"[^a-z ]", " ", n).strip()
    n = re.sub(r"\s+", " ", n)
    return n


_DIET_RANK = {"nonveg": 0, "egg": 1, "veg": 2}   # higher = more restricted


def _diet_floor(ings, allergens=()):
    """The loosest diet the ingredients permit, using the SAME whole-word matcher the
    safety gate uses. `infer_diet` compares keys by EXACT equality, so 'salmon fillet'
    never matched FLESH and dishes sat on the live feed labelled veg. This does not fix
    infer_diet; it refuses to let the repair leave such a dish mislabelled."""
    # A declared fish / shellfish token is itself proof of flesh, even when no
    # ingredient key spells it (4 Sep 2026).
    if _hits(ings, FLESH, FLESH_IMPOSTERS) or (set(allergens) & {"fish", "shellfish"}):
        return "nonveg"
    if _hits(ings, EGG):
        return "egg"
    return "veg"


def repair(doc):
    """Repair a loaded catalogue in place. Returns a dict of counts."""
    recipes = doc["recipes"] if isinstance(doc, dict) else doc
    before = {r["id"]: {"allergens": list(r.get("allergens") or []),
                        "diet": r.get("diet"),
                        "vegan": r.get("vegan"), "jain": r.get("jain"), "noOG": r.get("noOG"),
                        "ings": [(i.get("name"), i.get("qty")) for i in r.get("ingredients", [])],
                        "name": r.get("name"), "steps": r.get("steps")}
              for r in recipes}

    rows = 0
    for r in recipes:
        for ing in r.get("ingredients", []):
            nm, k = ing.get("name", ""), ing.get("key", "")
            ok, nk = _broken_ing_key(nm), ing_key(nm)
            if k == ok and ok != nk and nk:
                ing["key"] = nk
                rows += 1

    added_allergens = tightened = flags_off = 0
    for r in recipes:
        ings = r["ingredients"]
        stored = set(r.get("allergens") or [])
        gained = set(derive_allergens(ings)) - stored          # UNION, additions only
        if gained:
            r["allergens"] = sorted(stored | gained)
            added_allergens += 1

        floor = _diet_floor(ings, r.get("allergens") or [])
        if _DIET_RANK[floor] < _DIET_RANK.get(r.get("diet"), 2):
            r["diet"] = floor
            tightened += 1

        nv, nj, nn = derive_flags(ings, r["diet"])
        off = False
        for fld, val in (("vegan", nv), ("jain", nj), ("noOG", nn)):
            if r.get(fld) and not val:
                r[fld] = False
                off = True
        if off:
            flags_off += 1
            if "vegan" in r.get("tags", []) and not r.get("vegan"):
                r["tags"] = [t for t in r["tags"] if t != "vegan"]

    # ⚠️ the monotone promise, checked in code
    removed = loosened = restored = 0
    for r in recipes:
        b = before[r["id"]]
        if set(b["allergens"]) - set(r.get("allergens") or []):
            removed += 1
        if _DIET_RANK.get(r["diet"], 2) > _DIET_RANK.get(b["diet"], 2):
            loosened += 1
        for fld in ("vegan", "jain", "noOG"):
            if r.get(fld) and not b[fld]:
                restored += 1
        assert [(i.get("name"), i.get("qty")) for i in r["ingredients"]] == b["ings"], \
            f"{r['id']}: an ingredient name or quantity changed"
        assert all(i["key"] for i in r["ingredients"]), f"{r['id']}: a key went empty"
        assert r["name"] == b["name"] and r.get("steps") == b["steps"], \
            f"{r['id']}: name or steps changed"
    assert removed == 0, f"MONOTONE BROKEN: {removed} recipes lost an allergen"
    assert loosened == 0, f"MONOTONE BROKEN: {loosened} recipes had their diet loosened"
    assert restored == 0, f"MONOTONE BROKEN: {restored} restriction flags were switched ON"

    fails = [(r["id"], is_safe(r)[1]) for r in recipes if not is_safe(r)[0]]
    assert not fails, f"repair left {len(fails)} recipes failing the safety gate: {fails[:5]}"

    return {"rows": rows, "recipes": len(recipes), "allergens_added": added_allergens,
            "diet_tightened": tightened, "flags_off": flags_off}



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="catalog.json")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--repair", action="store_true",
                    help="one-off: fix ingredient keys the pre-1 Sep 2026 ing_key corrupted, "
                         "monotonically. Never removes an allergen. Does not harvest.")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    if a.repair:
        doc = json.load(open(a.catalog))
        n = repair(doc)
        doc["version"] = doc.get("version", 1) + 1
        json.dump(doc, open(a.catalog, "w"), ensure_ascii=False, separators=(",", ":"))
        print(f"repaired {n['rows']} ingredient rows across {n['recipes']} recipes; "
              f"{n['allergens_added']} recipes gained a previously-hidden allergen, "
              f"{n['diet_tightened']} diets tightened, {n['flags_off']} restriction flags "
              f"switched off; 0 allergens removed; feed v{doc['version']}")
        return
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
