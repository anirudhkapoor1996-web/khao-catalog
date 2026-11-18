#!/usr/bin/env python3
"""Khao diet checker (his order 18 Nov 2026 09:02/09:04: "a checker that manually checks every dish for being gluten free,
jain, allergen safe for each user ... probably should include halal and kosher too").

It does NOT trust a dish's tags. It reads every ingredient of every dish (key and full name) against written rules and works
out, for each dish:
  gf      "yes" | "if" (safe only with a gluten-free version of one ingredient, e.g. hing, oats, stock cube) | "no"
  jain    true/false (no meat, fish, egg, onion, garlic, roots and bulbs, mushroom, honey, alcohol, gelatin)
  halal   "yes" | "if" (fits halal only with halal meat / halal-certified cheese or gelatin) | "no" (pork, alcohol, blood)
  kosher  "yes" | "if" (kosher meat, kosher-certified cheese, wine or gelatin) | "no" (pork, shellfish, non-kosher fish,
          meat cooked with dairy, other non-kosher animals)
  allergens  the 10 allergen groups, re-derived from the ingredients
and the reasons (which ingredient decided it), under "dietWhy".

Safety direction: the checker only ever makes a dish STRICTER. It adds allergens the dish was missing and turns jain off when
an ingredient breaks it. It never removes an allergen or turns jain on by itself; those cases go in the report for a person.

  python3 diet_check.py            check, write diet_report.json, change nothing
  python3 diet_check.py --apply    also write the results into catalog.json (bumps version)
  python3 diet_check.py --verify   exit 1 if any dish lacks the fields or breaks a rule (used by the order check)
"""
import json, re, sys
from collections import Counter

CAT = "catalog.json"


def rx(words):
    return re.compile(r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])")


# ---- ingredient groups (lower-case, matched as whole words in "key | name") --------------------------------------------
PORK = rx(["pork", "ham", "bacon", "lard", "chorizo", "salami", "prosciutto", "pancetta", "nduja", "kielbasa", "kabanos",
           "morcilla", "black pudding", "pigs? trotters?", "serrano ham", "jam[oó]n.*", "pork belly.*", "sausages?",
           "italian fennel sausages", "german sausages", "polish kabanos", "streaky bacon", "bacon lardon", "deli ham",
           "turkey ham", "smoked ham", "mincemeat", "suet", "hot dog"])
# sausages/suet/mincemeat/hot dog: usually pork or beef fat of unknown slaughter -> treated as pork-risk for halal/kosher;
# "chicken sausages" and "turkey ham" are handled as meat (not pork) below.
NOT_PORK = rx(["chicken sausages?", "turkey ham", "vegan sausages?", "veg(?:etarian)? sausages?", "jam", "ham(?:burger)?\\s+buns?"])
ALCOHOL = rx(["wine", "white wine", "red wine", "dry white wine", "cooking wine", "rice ?wine", "shaoxing wine", "sherry",
              "dry sherry", "sweet sherry", "sherry cooking wine", "beer", "dark beer", "ale", "stout", "rum", "dark rum",
              "brandy", "ginger brandy", "cognac", "kirsch", "grand marnier", "sake", "mirin", "cider", "vodka", "whisk(?:e)?y",
              "tequila", "gin", "liqueur", "red wine jelly", "port"])
NOT_ALCOHOL = rx(["wine vinegar", "red wine vinegar", "white wine vinegar", "sherry vinegar", "cider vinegar",
                  "apple cider vinegar", "rice vinegar", "seasoned rice vinegar", "rice wine vinegar", "wine vinaigrette", "red wine vinaigrette", "ginger cordial", "porridge.*",
                  "portobello", "vegan white wine vinegar", "ginger(?! brandy)"])
GELATIN = rx(["gelatin(?:e)?", "gelatine leafs?", "gelatin sheet", "gelatin powder", "unflavoured gelatin", "aspic",
              "marshmallows?", "miniature marshmallows", "turkish delight"])
BLOOD = rx(["black pudding", "morcilla", "blood"])
MEAT = rx(["chicken.*", "mutton.*", "lamb.*", "beef.*", "veal.*", "goat meat", "duck.*", "turkey.*", "keema", "minced meat",
           "meat", "shredded meat", "doner meat", "oxtail", "liver", "chicken liver", "lamb kidney", "steak.*", "sirloin.*",
           "brisket", "beef brisket", "chuck roast", "flank steak", "skirty steak", "hind shank", "osso buco", "frogs legs",
           "corned beef", "mince", "lamb mince", "mutton mince", "turkey mince", "boneless chicken.*", "whole chicken",
           "chicken thighs?", "chicken wings", "chicken breasts?", "chicken drumsticks", "chicken stock.*", "beef stock.*",
           "chicken broth", "beef broth", "bone broth", "lamb stock", "mutton stock", "brown chicken stock",
           "chicken bouillon.*", "beef bouillon.*", "beef gravy", "bouillon cubes", "chicken ramen bone broth",
           "lamb fat", "fillet of steak", "tenderloin.*", "mixed beef cuts", "lean minced.*", "mutton chops",
           "short ribs", "pork.*", "bacon", "ham", "sausages?", "chorizo", "salami", "prosciutto", "cooked tandoori chicken.*",
           "fish cake", "mutton chaap", "goose fat"])
NOT_MEAT = rx(["vegetable stock.*", "veg(?:etable)? broth", "soya chunks", "mince pies?", "mincemeat", "meat masala",
               "chicken masala", "tata sampann chicken masala", "minced garlic", "garlic minced", "ginger minced",
               "shallot minced", "minced ginger", "turkish delight", "keema masala", "vegan.*", "jackfruit"])
NONKOSHER_SEA = rx(["prawns?", "shrimps?", "king prawns", "tiger prawns", "raw king prawns", "raw tiger prawns", "jumbo shrimp",
                    "crab.*", "lobster", "clams?", "mussels?", "oysters?", "oyster sauce", "oystersauce", "squid", "baby squid",
                    "calamari", "octopus", "scallops?", "crayfish", "crawfish", "conchs?", "shrimp ?paste", "salted ?shrimp",
                    "prawn ?stock", "shrimp stock", "seafood stock", "frozen seafood mix", "eel", "catfish", "shark",
                    "monkfish", "frogs legs", "prahok", "anchovystock", "sea urchin"])
# anchovy, sardine, herring, salmon, cod, tuna, haddock, hake, trout, mackerel, sea bass, barramundi, pilchards: fins and scales
SHELLFISH = rx(["prawns?", "shrimps?", "king prawns", "tiger prawns", "raw king prawns", "raw tiger prawns", "jumbo shrimp",
                "raw frozen prawns", "crab.*", "lobster", "clams?", "mussels?", "oysters?", "oyster sauce", "oystersauce", "squid",
                "baby squid", "calamari", "octopus", "scallops?", "crayfish", "crawfish", "conchs?", "shrimp ?paste",
                "salted ?shrimp", "prawn ?stock", "shrimp stock", "seafood stock", "frozen seafood mix", "saltedshrimp", "shrimppaste"])
FISH = rx(["fish.*", "salmon", "smoked salmon", "hot smoked flaked salmon", "tuna", "tinned tuna", "can skipjack tuna",
           "canned tuna.*", "cod", "salt cod", "codfish.*", "anchov(?:y|ies).*", "sardines?", "herring", "mackerel", "haddock",
           "smoked haddock", "hake", "trout", "rainbow trout", "sea bass.*", "barramundi", "pilchards", "monkfish", "white fish",
           "fish fillet", "fish sauce", "fishsauce", "fish stock", "dashi", "bonito", "katsuobushi", "worcestershire.*",
           "caesar dressing", "garum", "prahok", "furikake", "anchovystock", "goraka fish"])
NOT_FISH = rx(["fish ?cake mix", "goraka"])
EGG = rx(["eggs?", "egg yolks?", "egg whites?", "egg wash", "whole eggs?", "free range eggs?.*", "eggs room temperature",
          "hard boiled egg.*", "boiled egg.*", "eggs boiled.*", "mayo(?:nnaise)?", "meringue.*", "custard", "egg noodles",
          "egg rolls?", "egg roll wrappers", "aioli", "a oli", "smoky a oli", "brioche.*", "tempura flour", "marzipan",
          "nougatine", "caesar dressing", "pasta.*egg", "lasagne sheets", "fresh pasta"])
NOT_EGG = rx(["eggplants?", "egg plants?", "flax eggs?", "vegan.*", "baby eggplants", "custard powder"])
DAIRY = rx(["milk", "whole milk", "milk powder", "butter", "unsalted butter", "salted butter", "melted butter", "chilled butter",
            "butter melted", "plain butter", "oil butter", "butter or oil", "ghee.*", "pure ghee", "cream", "double cream",
            "single cream", "heavy cream", "whipping cream", "sour cream", "full fat sour cream", "soured cream.*", "thick cream",
            "clotted cream", "unsweetened dairy cream", "creme fraiche", "cr[eè]me fra[iî]che", "curd.*", "thick curd",
            "whisked curd", "thick whisked curd", "yog(?:h)?urt.*", "greek yogurt", "natural yoghurt", "plain yog(?:h)?urt.*",
            "beaten yogurt", "strained yoghurt", "full fat yogurt", "thick yogurt", "skyr.*", "paneer", "cheese.*",
            "\\w+ cheese", "cheddar.*", "mozzarella.*", "mozarella", "parmesan.*", "parmigiano.*", "grana padano.*", "pecorino",
            "feta", "cubed feta cheese", "ricotta", "mascarpone", "halloumi", "brie", "labneh", "quark", "sweet quark",
            "fromage frais", "farmers cheese", "cottage ?cheese", "cream cheese", "queso fresco", "manchego", "gruy[eè]?re.*",
            "gruy re", "emmentaler.*", "stilton.*", "gouda.*", "goats cheese", "khoya", "malai", "buttermilk", "sour buttermilk",
            "whey", "condensed ?milk", "sweetened condensed milk", "evaporated milk", "ice ?cream", "dulce de leche",
            "custard", "bechamel", "tzatziki", "white chocolate.*", "milk chocolate", "chocolate chips", "toffee.*", "caramel.*",
            "liquid cheese", "cheese curds", "raita", "lassi", "kulfi", "rabri", "shrikhand", "chhena", "kalakand", "pesto",
            "naan bread", "curd or yogurt", "skyr or greek yogurt", "ghee for smoking", "oil or ghee", "fudge", "brioche.*",
            "soured cream and chive dip", "caesar dressing", "vanilla protein powder"])
NOT_DAIRY = rx(["coconut ?milk", "coconutmilk", "unsweetened coconut milk", "coconut cream", "almond milk", "soy ?milk", "soya milk",
                "soymilk", "oat milk", "vegetable millk", "vegan butter", "peanut butter", "cocoa butter", "nut butter",
                "butter beans", "butternut.*", "roasted butternut squash puree", "butterfly", "dairy[- ]free.*", "vegan.*",
                "bean ?curd", "fermented ?bean ?curd", "beancurd", "fermentedbeancurd", "custard powder", "cream of tartar",
                "ice cubes", "coconut", "creamed corn", "milk thistle", "cashew cream"])
GLUTEN_NO = rx(["wheat", "wheat flour", "whole wheat.*", "flour", "plain flour.*", "all purpose flour", "self raising flour",
                "bread flour.*", "strong (?:white )?(?:bread )?flour", "strong wholemeal flour", "good quality white flour",
                "white flour", "flour water", "strong flour", "maida", "atta", "semolina.*", "rava", "suji", "sooji", "couscous",
                "bulgur.*", "freekeh", "barley", "rye.*", "spelt", "seitan", "bread.*", "\\w+ bread", "white bread.*",
                "crusty bread", "rustic bread", "stale bread", "bread slices", "bread rolls", "multi ?grain bread.*", "toast",
                "pav", "buns?", "brioche.*", "naan.*", "roti", "rotis?", "khamiri roti", "rumali rotis?.*", "parantha", "paratha",
                "warqi parantha.*", "puri", "papdi", "kulcha", "bhatura", "pita.*", "pitta.*", "flour tortilla", "tortillas?",
                "wraps?", "wrappers?", "wonton.*", "dumpling wrappers?", "egg roll wrappers", "rice flour pancakes",
                "pasta.*", "\\w+ pasta", "spaghetti", "macaroni", "fettuccine", "linguine.*", "penne.*", "rigatoni", "farfalle",
                "paccheri.*", "bowtie pasta", "lasagne sheets", "gnocchi", "noodles", "egg noodles", "ramen noodles",
                "udon noodles", "maggi", "vermicelli", "vermicelli pasta", "sevaiiya", "soy ?sauce", "soysauce", "dark ?soy.*",
                "light soy sauce", "soya sauce", "thai soy sauce", "kecap ?manis", "kecapmanis", "breadcrumbs",
                "coarse breadcrumbs", "panko", "puff pastry", "filo.*", "phyllo dough", "shortcrust pastry", "pastry",
                "ready rolled shortcrust pastry", "pizza dough", "dough", "biscuits?", "digestive biscuits", "crackers",
                "graham cracker crumbs", "maria cookies", "oreo cream biscuits", "peanut cookies", "gingersnap", "pretzels?",
                "cake", "muffin", "english muffins", "pancake", "beer", "dark beer", "ale", "stout", "malt.*", "corn flakes",
                "rice krispies", "grape nut cereal", "tempura flour", "curry roux", "kataifi", "knafeh", "seviyan",
                "christmas pudding", "mincemeat", "suet", "tonkatsu sauce", "okonomi sauce", "hoisin.*", "oyster ?sauce",
                "oystersauce", "black ?bean ?paste", "blackbeanpaste", "bean ?sauce", "beansauce", "gochujang", "hot pepper paste",
                "doubanjiang", "chilli ?bean ?paste", "chillibeanpaste", "worcestershire.*", "teriyaki", "sausages?",
                "italian fennel sausages", "german sausages", "kabanos sausages", "falafel", "fries", "hard taco shells",
                "injera", "dosa batter", "bechamel", "plain flour for breading", "breadfruit flour", "frozen potato wedges",
                "boondi", "sev", "bhujia", "farsan", "papad", "rice papad or fried rice noodles", "khus khus", "white bread mix",
                "egg rolls?", "speculaas spice mix", "mars bar", "toffee popcorn", "nougatine", "fish cake", "patty",
                "cuban bread", "sesame seed burger buns", "hot dog buns", "brioche buns toasted", "ciabatta", "baguette",
                "sourdough starter", "pudding", "custard", "caesar dressing"])
# things that LOOK like gluten but are not
GLUTEN_OK = rx(["rice flour.*", "riceflour", "tbsps rice flour", "rice flour fine", "sweet rice flour", "sticky rice flour",
                "glutinous rice", "rice noodles?", "ricenoodles", "rice stick noodles", "rice vermicelli", "vermicelli rice noodles",
                "brown rice noodle", "glass ?noodles", "glassnoodles", "shirataki", "rice paper.*", "rice cake", "corn ?flour",
                "cornflour.*", "corn tortillas", "masa", "yellow masarepa", "corn arepa.*", "cornmeal", "fine yellow cornmeal",
                "white cornmeal", "chickpea flour", "gram flour.*", "roasted gram flour", "tbsps roasted gram flour",
                "besan", "singhara.*", "singhara flour", "kuttu.*", "kuttu flour", "buckwheat.*", "buckwheat flour",
                "rajgira.*", "rajgira flour", "ragi.*", "ragi flour", "bajra.*", "bajra flour", "jowar", "makki", "teff", "cassava.*",
                "cassava flour", "tapioca", "sabudana", "potato starch.*", "starch", "almond flour", "almond powder", "coconut flour",
                "oat flour or arrowroot", "arrowroot", "idli batter", "appam batter", "mungflour", "quinoa", "samak", "millet",
                "tamari", "sorghum", "makhana", "poha", "murmura", "puffed rice", "polenta", "grits", "hominy",
                "cream of tartar", "buckwheat", "potato wedges", "flourless", "casabe", "farine", "dosa batter",
                "boondi", "sev", "bhujia", "farsan", "papad"])
# boondi, sev, bhujia, farsan, papad, dosa batter: normally besan/rice/urad - kept in GLUTEN_OK, but sold mixes can carry wheat:
GLUTEN_IF = rx(["hing", "asafo?e?tida.*", "asafortida heeng", "heeng", "oats", "rolled oats", "porridge oats", "ground oats",
                "oatmeal", "granola", "stock ?cubes?", "\\w+ stock cubes?", "chicken stock cube", "vegetable stock cube",
                "bouillon.*", "\\w+ bouillon.*", "chicken bouillon.*", "beef stock concentrate", "all purpose seasoning",
                "miso", "soybeanpaste", "soybean paste", "curry paste", "red curry paste", "thai red curry paste",
                "green curry paste", "thai green curry paste", "massaman.*", "laksa paste", "panang curry paste",
                "bbq sauce", "barbeque sauce", "ketchup", "tomato ketchup", "salad dressing", "vinaigrette.*",
                "sauce", "chilli sauce", "sweet chilli sauce", "schezwan sauce", "mala sauce", "duck sauce", "plum sauce",
                "enchilada sauce", "beef gravy", "gravy", "msg", "dashi", "furikake", "chocolate.*", "dark chocolate.*",
                "chocolate chips", "ice ?cream", "icecream", "custard powder", "baking powder", "bakingpowder", "dried chilli",
                "garam masala", "sambhar masala.*", "sambar powder", "biryani masala", "pav bhaji masala", "chole masala",
                "spice mix", "seasoning", "italian seasoning", "bbq rub",
                "rasam powder", "curry powder", "currypowder", "jamaican curry powder", "tandoori masala",
                "chaat masala", "vanilla protein powder", "soba", "dosa batter", "boondi", "sev", "bhujia", "farsan", "papad",
                "maggi", "kimchi", "gochugaru", "sazon.*", "fajita seasoning", "jerk", "cajun",
                "suya spice", "imitation crab", "crab meay", "fish cake", "veggie burger", "bread crumbs gluten free"])
NUTS = rx(["cashews?.*", "cashew ?nuts?", "cashewnut paste", "cashew nut paste", "raw cashews", "almonds?.*", "almond.*",
           "ground almonds", "flaked almonds", "almond flour", "almond powder", "almond milk", "almond extract", "almond essence",
           "almond paste", "marzipan", "pistachios?.*", "ground pistachios", "pistachio paste", "unsalted pistachio",
           "walnuts?", "ground walnuts", "pecans?.*", "pecan nuts", "hazel ?nuts?.*", "hazlenuts", "shelled hazelnuts",
           "pine ?nuts", "pinenuts", "macadamia.*", "brazil nuts?", "nuts", "mixed nuts", "nougatine", "praline",
           "candlenut", "chestnuts?", "cooked chestnut", "nut butter", "pesto", "almonds and cashew nuts slivered",
           "baklava", "kataifi", "knafeh", "turkish delight", "ground mahleb"])
NOT_NUTS = rx(["coconut.*", "nutmeg.*", "grated nutmeg", "ground nutmeg", "peanut.*", "ground nut oil", "groundnut.*",
               "butternut.*", "water chestnut", "doughnut", "makhana.*", "fox ?nuts?", "\\(fox nuts\\)", "chestnut mushroom.*", "donut", "betel nut"])
# coconut is not a tree-nut allergen group in India/EU labelling; water chestnut is a vegetable
PEANUT = rx(["peanuts?.*", "roasted peanut", "unsalted peanuts", "raw peanuts.*", "peanut butter", "peanut oil", "peanut powder",
             "peanut brittle", "peanut cookies", "ground ?nut oil", "groundnut.*", "satay", "chikki", "kecap.*peanut"])
SOY = rx(["soy.*", "soya.*", "soy ?sauce", "soysauce", "dark ?soy.*", "light soy sauce", "thai soy sauce", "soya sauce",
          "soya chunks", "soya bean", "soybean.*", "soymilk", "soy ?milk", "tofu", "firm tofu", "silken tofu", "extra firm tofu.*",
          "marinated tofu", "tempeh", "edamame", "miso", "tamari", "bean ?curd", "beancurd", "fermented ?bean ?curd",
          "fermentedbeancurd", "kecap ?manis", "kecapmanis", "doubanjiang", "black ?bean ?paste", "blackbeanpaste",
          "fermented black beans", "teriyaki", "hoisin.*", "bean ?sauce", "beansauce", "gochujang", "hot pepper paste",
          "tonkatsu sauce", "okonomi sauce", "ponzu", "worcestershire.*", "natto", "yuba", "chilli ?bean ?paste",
          "chillibeanpaste", "vegetable shortening", "brown sugar replacement", "furikake", "duck sauce", "mala sauce",
          "schezwan sauce", "maggi"])
NOT_SOY = rx(["soy-free.*"])
SESAME = rx(["sesame.*", "white sesame seeds", "toasted sesame seeds", "roasted sesame seeds", "sesame seeds?",
             "sesame seed oil", "sesameoil", "sesame oil", "tahini.*", "tahini paste", "til", "gingelly.*", "hummus",
             "furikake", "zaatar", "za'atar", "chinese sesame sauce", "sesame seed burger buns", "gomasio",
             "chilli flakes spring onion sesame seeds", "dukkah"])
MUSTARD = rx(["mustard.*", "mustard seeds", "mustard oil", "mustardoil", "mustard powder", "yellow mustard", "dijon mustard",
              "english mustard", "wholegrain mustard", "ground mustard", "panch ?phoron", "panchphoron", "kasundi",
              "achar masala", "pickle", "salad dressing", "vinaigrette.*", "mayo(?:nnaise)?", "caesar dressing",
              "rasam powder", "sambar powder", "sambhar masala.*", "malvani ?masala", "malvanimasala",
              "preservedmustard", "mustard greens"])
NOT_MUSTARD = rx(["pickle juice", "dill pickles", "pickled garlics?", "pickledgarlic", "pickled scallion.*", "pickled grape leaves",
                  "mustard-free.*"])
ONION_GARLIC = rx(["onions?.*", "red onions?", "brown onions?", "big onion", "golden onions", "grated onion", "onion paste",
                   "onion powder", "onion salt", "ground onion", "fried onion.*", "onions fried golden", "onions and fried",
                   "browned onion paste", "yellow or white onion diced", "spring ?onions?.*", "springonion", "green onions?",
                   "scallions?", "shallots?.*", "challots", "leeks?", "chives?", "garlic.*", "\\w+ garlic", "ginger ?garlic.*",
                   "toum", "garlic chutney", "wild garlic leaves", "pickled ?garlics?", "pickledgarlic", "aioli", "a oli",
                   "smoky a oli", "gremolata", "pesto", "tzatziki", "chimichurri sauce", "salsa", "green salsa", "pico de gallo.*",
                   "harissa.*", "sambal", "berbere", "mitmita", "kimchi", "garlic sauce", "garlic granules", "garlic salt",
                   "garlic powder", "garlic bulb", "garlic heads", "garlic juice", "sofrito", "shawarma spice",
                   "ras el hanout", "fajita seasoning", "all purpose seasoning", "cajun", "jerk", "suya spice",
                   "sazon.*", "massaman.*", "laksa paste", "curry paste", "red curry paste",
                   "green curry paste", "thai red curry paste", "thai green curry paste", "panang curry paste", "chilli oil",
                   "crispy chilli oil", "schezwan sauce", "mala sauce", "gochujang", "doubanjiang", "fried garlic"])
ROOTS = rx(["potato(?:es)?.*", "\\w+ potato(?:es)?", "new potatoes", "baby new potatoes", "jersey royal potatoes", "russet.*",
            "charlotte potatoes", "floury potatoes", "yellow potatoes", "red potatoes", "frozen potato wedges", "fries",
            "sweet ?potato(?:es)?", "sweetpotato", "carrots?.*", "carrot grated", "carrot cubes", "beet(?:root)?s?.*",
            "cooked beetroot", "radish(?:es)?.*", "red radishes", "radish sprouts", "daikon.*", "turnips?.*", "swede", "parsnips?",
            "celeriac", "jerusalem artichokes", "yam", "white yam", "yautia", "arbi", "colocasia", "taro.*", "taroleaves", "cassava.*",
            "yuca", "raw yucca", "cassaba", "ginger.*", "\\w+ ginger", "ginger ?garlic.*", "ginger root", "ginger paste",
            "ginger juice", "ginger julienne", "julienned ginger.*", "freshly grated ginger", "ginger grated", "ginger finely",
            "ginger minced", "galangal.*", "turmeric root", "lotus ?stem", "lotusstem", "lotus root", "nadru",
            "mushrooms?.*", "\\w+ mushrooms", "shiitake mushrooms", "oyster mushrooms", "white mushrooms", "wild mushrooms",
            "woodear", "truffle oil", "bamboo ?shoots?", "bambooshoot", "bamboo", "long pepper root", "vetiver roots",
            "ratanjot", "kombu", "potato starch.*", "aloo", "suran", "kand", "mooli", "raw banana", "raw bananas"])
JAIN_ROOT_OK = rx(["ginger powder", "dry ginger powder", "ground ginger", "sonth", "saunth", "ginger cordial",
                   "turmeric powder", "ground turmeric", "haldi", "potato starch.*"])
# raw banana: allowed by most Jains (not a root) -> removed from ROOTS effect below
JAIN_OTHER = rx(["honey", "clear honey", "honey lemon juice", "yeast", "instant yeast", "dry yeast", "fast action yeast",
                 "sourdough starter", "brinjal.*", "aubergines?", "baby aubergine", "baingan", "eggplants?", "egg plants",
                 "baby eggplants", "cauliflower", "broccoli.*", "purple sprouting broccoli"])
# yeast/honey/brinjal/cauliflower: avoided by strict Jain practice (fermentation, bee harm, many seeds, hidden insects)
VEG_SAFE_FATS = rx(["vegan.*"])


def text_of(ing):
    return (ing.get("key", "") + " | " + ing.get("name", "")).lower()


def hit(pat, neg, t):
    if not pat.search(t):
        return False
    if neg is not None:
        # remove the excluded phrases, then look again
        t2 = neg.sub(" ", t)
        return bool(pat.search(t2))
    return True


def check_dish(d):
    ings = [text_of(i) for i in d.get("ingredients", [])]
    why = {"gf": [], "jain": [], "halal": [], "kosher": [], "allergens": {}}
    al = set()

    def add_al(name, t):
        al.add(name)
        why["allergens"].setdefault(name, []).append(t.split(" | ")[-1][:40])

    has_meat = has_dairy = False
    gf = "yes"; halal = "yes"; kosher = "yes"; jain = True
    for t in ings:
        nm = t.split(" | ")[-1][:40]
        # a named non-pork sausage/ham ("chicken sausage", "turkey ham") anywhere in the line wins over the bare key
        pork = hit(PORK, NOT_PORK, t) and not NOT_PORK.search(t.split(" | ")[-1])
        alcohol = hit(ALCOHOL, NOT_ALCOHOL, t)
        meat = (hit(MEAT, NOT_MEAT, t) or pork)
        fish = hit(FISH, NOT_FISH, t)
        shell = hit(SHELLFISH, None, t)
        egg = hit(EGG, NOT_EGG, t)
        dairy = hit(DAIRY, NOT_DAIRY, t)
        # gluten
        if hit(GLUTEN_NO, GLUTEN_OK, t):
            gf = "no"; why["gf"].append(nm); add_al("gluten", t)
        elif hit(GLUTEN_IF, GLUTEN_OK if not re.search(r"dosa batter|boondi|\bsev\b|bhujia|farsan|papad", t) else None, t):
            if gf == "yes":
                gf = "if"
            why["gf"].append(nm + " (needs a gluten-free one)")
        # allergens
        if dairy: add_al("dairy", t); has_dairy = True
        if egg: add_al("egg", t)
        if fish: add_al("fish", t)
        if shell: add_al("shellfish", t)
        if hit(NUTS, NOT_NUTS, t): add_al("nuts", t)
        if hit(PEANUT, None, t): add_al("peanut", t)
        if hit(SOY, NOT_SOY, t): add_al("soy", t)
        if hit(SESAME, None, t): add_al("sesame", t)
        if hit(MUSTARD, NOT_MUSTARD, t): add_al("mustard", t)
        # jain
        if meat or fish or shell or egg:
            jain = False; why["jain"].append(nm + " (meat, fish or egg)")
        elif hit(ONION_GARLIC, None, t):
            jain = False; why["jain"].append(nm + " (onion or garlic)")
        elif hit(ROOTS, JAIN_ROOT_OK, t) and not re.search(r"raw bananas?", t):
            jain = False; why["jain"].append(nm + " (root, bulb or mushroom)")
        elif alcohol or hit(GELATIN, None, t) or hit(JAIN_OTHER, None, t):
            jain = False; why["jain"].append(nm + " (honey, yeast, alcohol, gelatin or many-seeded vegetable)")
        # halal
        if pork or alcohol or hit(BLOOD, None, t):
            halal = "no"; why["halal"].append(nm + (" (pork)" if pork else " (alcohol)" if alcohol else " (blood)"))
        elif hit(GELATIN, None, t):
            if halal == "yes": halal = "if"
            why["halal"].append(nm + " (needs halal-certified gelatin)")
        elif meat:
            if halal == "yes": halal = "if"
            why["halal"].append(nm + " (needs halal meat)")
        elif re.search(r"vanilla extract|pure vanilla extract|vanilla essence", t):
            if halal == "yes": halal = "if"
            why["halal"].append(nm + " (alcohol-free vanilla)")
        # kosher
        if pork or hit(NONKOSHER_SEA, None, t) or hit(BLOOD, None, t):
            kosher = "no"; why["kosher"].append(nm + " (not kosher)")
        elif alcohol and re.search(r"wine|sherry|brandy|cognac|grand marnier|kirsch|port", t):
            if kosher == "yes": kosher = "if"
            why["kosher"].append(nm + " (needs kosher wine)")
        elif hit(GELATIN, None, t):
            if kosher == "yes": kosher = "if"
            why["kosher"].append(nm + " (needs kosher gelatin)")
        elif meat:
            if kosher == "yes": kosher = "if"
            why["kosher"].append(nm + " (needs kosher meat)")
            has_meat = True
        elif re.search(r"cheese|paneer|parmesan|parmigiano|pecorino|mozzarella|mozarella|cheddar|feta|halloumi|ricotta|"
                       r"mascarpone|brie|gouda|gruy|stilton|emmentaler|manchego|labneh|chhena", t):
            if kosher == "yes": kosher = "if"
            why["kosher"].append(nm + " (needs kosher-certified cheese)")
        if meat:
            has_meat = True
    if has_meat and has_dairy and kosher != "no":
        kosher = "no"; why["kosher"].append("meat cooked with dairy")
    if (has_meat or any(hit(FISH, NOT_FISH, t) for t in ings)) and any(
            re.search(r"cheese|paneer|ricotta|mascarpone|halloumi", t) for t in ings) and halal == "yes":
        halal = "if"; why["halal"].append("cheese (needs halal-certified rennet)")
    if halal == "yes" and any(re.search(r"cheese|paneer|parmesan|parmigiano|pecorino|grana padano|gruy|manchego|emmentaler|stilton|gouda|brie", t)
                              and not re.search(r"cream cheese|cottage", t) for t in ings):
        if any(re.search(r"parmesan|parmigiano|pecorino|grana padano|gruy|manchego|emmentaler|stilton|gouda|brie|cheddar|mozzarella|mozarella|\bcheese\b", t) for t in ings):
            halal = "if"; why["halal"].append("hard cheese (needs halal-certified rennet)")
    return {"gf": gf, "jain": jain, "halal": halal, "kosher": kosher, "allergens": sorted(al), "why": why}


ORDER = ["dairy", "gluten", "egg", "soy", "nuts", "sesame", "peanut", "fish", "mustard", "shellfish"]


def main():
    c = json.load(open(CAT))
    R = c["recipes"]
    rep = {"version_checked": c["version"], "dishes": len(R), "added_allergens": [], "jain_turned_off": [],
           "jain_maybe_on": [], "allergen_maybe_extra": [], "diet_conflicts": [], "counts": {}}
    out = {}
    for d in R:
        r = check_dish(d)
        out[d["id"]] = r
        old_al = set(d.get("allergens", []))
        new_al = set(r["allergens"])
        for a in sorted(new_al - old_al):
            rep["added_allergens"].append([d["id"], d["name"], a, r["why"]["allergens"].get(a, [])[:3]])
        for a in sorted(old_al - new_al):
            rep["allergen_maybe_extra"].append([d["id"], d["name"], a])
        if d.get("jain") and not r["jain"]:
            rep["jain_turned_off"].append([d["id"], d["name"], r["why"]["jain"][:3]])
        if not d.get("jain") and r["jain"] and d.get("diet") == "veg":
            rep["jain_maybe_on"].append([d["id"], d["name"]])
        meatish = any(hit(MEAT, NOT_MEAT, text_of(i)) or hit(FISH, NOT_FISH, text_of(i)) or hit(SHELLFISH, None, text_of(i))
                      for i in d["ingredients"])
        eggish = any(hit(EGG, NOT_EGG, text_of(i)) for i in d["ingredients"])
        if d.get("diet") == "veg" and (meatish or eggish):
            rep["diet_conflicts"].append([d["id"], d["name"], "marked veg but has meat, fish or egg"])
        if d.get("vegan") and (meatish or eggish or "dairy" in new_al or any(
                re.search(r"honey|gelatin", text_of(i)) for i in d["ingredients"])):
            rep["diet_conflicts"].append([d["id"], d["name"], "marked vegan but has an animal product"])
    for k in ("gf", "halal", "kosher"):
        rep["counts"][k] = dict(Counter(o[k] for o in out.values()))
    rep["counts"]["jain"] = dict(Counter(o["jain"] for o in out.values()))
    for k in ("added_allergens", "jain_turned_off", "jain_maybe_on", "allergen_maybe_extra", "diet_conflicts"):
        rep["counts"][k] = len(rep[k])

    if "--verify" in sys.argv:
        bad = []
        for d in R:
            r = out[d["id"]]
            if any(k not in d for k in ("gf", "halal", "kosher", "dietWhy")):
                bad.append(d["id"] + " missing fields"); continue
            if d.get("jain") and not r["jain"]:
                bad.append(d["id"] + " marked jain but " + "; ".join(r["why"]["jain"][:2]))
            if set(r["allergens"]) - set(d.get("allergens", [])):
                bad.append(d["id"] + " missing allergens " + ",".join(sorted(set(r["allergens"]) - set(d["allergens"]))))
            rank = {"yes": 0, "if": 1, "no": 2}
            for k in ("gf", "halal", "kosher"):
                if rank.get(d.get(k), -1) < rank[r[k]]:
                    bad.append(d["id"] + " %s says %s, rules say %s" % (k, d.get(k), r[k]))
        print("diet check: %d dishes, %d problems%s" % (len(R), len(bad), (": " + " | ".join(bad[:5])) if bad else ""))
        sys.exit(1 if bad else 0)

    json.dump(rep, open("diet_report.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(rep["counts"], indent=1))
    if "--apply" in sys.argv:
        for d in R:
            r = out[d["id"]]
            d["allergens"] = [a for a in ORDER if a in set(d.get("allergens", [])) | set(r["allergens"])]
            if not r["jain"]:
                d["jain"] = False
            d["gf"] = r["gf"]; d["halal"] = r["halal"]; d["kosher"] = r["kosher"]
            d["dietWhy"] = {k: v[:4] for k, v in r["why"].items() if k != "allergens" and v}
        c["version"] = c["version"] + 1
        json.dump(c, open(CAT, "w"), ensure_ascii=False, separators=(",", ":"))
        print("applied -> version", c["version"])


if __name__ == "__main__":
    main()
