#!/usr/bin/env python3
"""Khao recipe restriction gate (AOS, 18 Nov 2026).

Checks EVERY dish, ingredient by ingredient (name + key + method text + dish name), for:
  veg / egg / non-veg, vegan, Jain, no-onion-garlic, gluten-free, lactose-free, halal, kosher,
  and the ten allergen groups.

Each dish gets (written into catalog.json with --apply):
  gf, lactoseFree, halal, kosher   each "yes" | "no" | "maybe" | "label"
        no     = a listed ingredient breaks it
        maybe  = the dish can go either way (variant-dependent: naan, bare noodles, meat that may not be halal-slaughtered)
        label  = fine on paper but a bought ingredient can carry it (hing, stock cube, vanilla extract): read the pack
  dietWhy    one line saying why, per attribute that is not "yes"
  checkAlerts  list of "attr:level:why" strings for every maybe/label/no  (the alert the apps/AOS can show)
and the stored vegan / jain / noOG / diet / allergens are made SAFER when they are less strict than the
ingredients prove. They are never relaxed automatically; a stored "no" that the ingredients do not support
goes on the review queue instead.

usage: recipe_gate.py CATALOG.json [--apply] [--report DIR]
"""
import json, re, sys, os, collections

# ---------------------------------------------------------------- normalisation
PROTECT = [
    (r"(rice )?sevai|idiyappam|idiappam|string hoppers?|rice vermicelli|rice sticks", "ricething"),
    (r"makhana|fox nuts?|lotus seeds?|phool makhana", "makhana"),
    (r"(cassava|turnip|radish|taro|yam|daikon) cake", "ricecake"),
    (r"sel roti|poulet roti|roti de|roti a", "gfitem"),
    (r"(dosa|idli|appam|hopper|dhokla|handvo|rice|urad|ferment(ed)?|uttapam|pesarattu|neer dosa|set dosa|khaman|thatte) ?(batter|mix)", "gfbatter"),
    (r"(akki|rice|jowar|jwari|bajra|ragi|makki|corn|millet|nachni|sorghum|besan|singhara|kuttu|sabudana|jolada|rajgira|samak|amaranth|buckwheat|thalipeeth|missi|quinoa|oats?|tapioca|sago|vari|bhagar|moraiya|sama) (roti|rotti|bhakri|paratha|chilla|cheela|dosa|puri|poori|flatbread|pancakes?|tikki|noodles?|cake|pudding|porridge)", "gfitem"),
    (r"(zucchini|zoodles?|veg|vegetable|sweet potato|konjac|shirataki|glass|cellophane|bean thread|mung bean|kelp|courgette|pumpkin|cucumber|spiralised|carrot|kelp) (noodles?|pasta|spaghetti)", "gfnoodle"),
    (r"fish ?cakes?|odeng|eomuk|fishcake", "fishcakeitem"),
    (r"(crab|prawn|shrimp) cakes?", "crabcakeitem"),
    (r"(rice|potato|tteok|sweet potato) cakes?|tteok", "ricecake"),
    (r"(spanish|espanola|de patatas|potato) tortilla|tortilla (espanola|de patatas)", "potatoomelette"),
    (r"corn tortillas?|maize tortillas?|tortilla chips?|taco shells?|tostadas?", "cornthing"),
    (r"\bhalwa\b|\bhalva\b", "mithaihalwa"),
    (r"tahini halva|sesame halva", "sesamehalva"),
    (r"(vegetarian|vegan|mushroom|veg|plant) oyster sauce", "mushroomsauce"),
    (r"\bteff\b( flour)?", "tefflour"),
    (r"(soya|soy|veg|vegetable|jackfruit|lentil|walnut|mushroom|paneer|tofu|plant|quorn|banana|raw banana|potato|aloo|cauliflower|beetroot|corn|hara bhara|bhara|dal|chana|rajma) (keema|mince|minced|kebabs?|kababs?|seekh|steaks?|sausages?|meatballs?|burgers?|nuggets?|cutlets?|ribs?)", "plantmeat"),
    (r"(keema|kebabs?|kababs?|seekh|kabab|steaks?) (of )?(soya|soy|veg|vegetable|jackfruit|paneer|tofu|mushroom)", "plantmeat"),
    (r"(soya|soy) (keema|chunks)", "plantmeat"),
    (r"(?<!chicken )(?<!turkey )(?<!meat )(?<!lamb )drumsticks?\b", "plantpart"),
    (r"(chicken|beef|pork|lamb|mutton|baby back|spare|short) (ribs?|wings?)", r"chicken \1"),
    (r"minced (garlic|ginger|onion|chillies|chilli|coriander|parsley|herbs|shallots?|lemongrass)", r"fresh \1"),
    (r"beef ?(steak )?tomato(es)?", "tomato"),
    (r"goat( s| es)? (cheese|milk|curd|yogh?urt)", r"cheese"),
    (r"custard powder|custard apple|custard mix", "cornpowder"),
    (r"(anda|egg) bhurji", "eggbhurji"), (r"\bbhurji\b", "bhurji_plain"),
    (r"mince ?(meat|pies?)|mincemeat", "fruitmince"),
    (r"(fermented )?(bean|tofu) curd", "beancurd"),
    (r"vegetarian dashi|kombu dashi|veg dashi", "kombu"),
    # phrases that LOOK like an issue word but are not; rewritten to neutral tokens first
    (r"coconut (milk|cream|oil|butter|water|flour|sugar)", r"coco_\1"),
    (r"peanut butter|groundnut butter", "peanutspread"),
    (r"(almond|cashew|hazelnut|walnut|pistachio|nut) (butter|milk|cream|paste)", "treenutspread"),
    (r"(soy|soya) (milk|cream|yogh?urt)", "soymilk"),
    (r"(sesame|sunflower|seed) butter", "seedspread"),
    (r"cocoa butter", "cocoabutter"), (r"shea butter", "sheabutter"),
    (r"butternut", "squash"), (r"butter ?(beans?|lettuce|cup)", "butterbean"),
    (r"egg ?plants?|aubergines?|baingan|brinjal", "aubergine"),
    (r"nut ?meg", "nutmegspice"), (r"cream of tartar", "tartar"),
    (r"(soy|soya|oat|almond|rice|cashew|plant|coconut|hemp|nut) (milk|cream|yogh?urt|cheese|curd)", r"plant_\2"),
    (r"(vegan|dairy[- ]free|plant[- ]based|veg) (butter|cheese|cream|milk|mayo|mayonnaise|yogh?urt)", r"plant_\2"),
    (r"vegan", "plantbased"),
    (r"water chestnut", "waterchestnut"), (r"pine ?nuts?", "pinenut"),
    (r"(rice|gram|chickpea|besan|makki|maize|sattu|singhar[ae]|singhade|kuttu|rajgira|corn|tapioca|potato|arrowroot|coconut|almond|singhara|kuttu|buckwheat|rajgira|amaranth|ragi|jowar|bajra|sorghum|millet|quinoa|samak|sabudana|water chestnut|lentil|gluten[- ]free) ?(flour|starch|atta)", "gffour"),
    (r"corn ?flour|cornstarch|corn starch|cornmeal|polenta|masa", "cornthing"),
    (r"gluten[- ]free (bread|pasta|noodles|flour|soy sauce|tamari)", "gfproduct"),
    (r"tamari", "tamari"), (r"rice (noodles?|paper|vermicelli|wrappers?|sticks?)", "ricething"),
    (r"buckwheat( noodles| soba)?", "buckwheat"),
    (r"(black|white|green|red|cayenne|sichuan|szechuan) ?pepper(corns?)?", "peppercorn"),
    (r"mustard (oil|seeds?)", "mustardseedoil"),
    (r"ginger ?bread", "gingerbread"),
    (r"(ice ?cream|gelato|kulfi)", "icecream"),
    (r"milk ?chocolate", "milkchocolate"),
    (r"horse ?radish", "horseradish"),
    (r"(jack)?fruit", "fruit"),
]
PROTECT = [(re.compile(a), b) for a, b in PROTECT]
POST = [(re.compile(a), b) for a, b in [
    (r"(waterchestnut|singhara|singhare|singhade|water chestnut)( waterchestnut| water chestnut)? (flour|atta|atte)( ka| ke)?", "gffour"),
    (r"rice (rava|rawa|suji|sooji|semolina)", "gffour"),
    (r"(vermicelli|brown|thin|flat|wide|dried|fresh|glass) (ricething|gfitem|gfnoodle)", "ricething"),
    (r"(ricething|gffour|rice|ricecake|gfitem|gfnoodle) (idiyappam )?(noodles?|vermicelli|pancakes?|sevai|crepes?)", "ricething"),
    (r"gffour (pancakes?|noodles?)", "ricething"),
]]


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for rx, rep in PROTECT:
        s = rx.sub(rep, s)
    for rx, rep in POST:
        s = rx.sub(rep, s)
    return " " + s + " "


# ---------------------------------------------------------------- knowledge: (regex, {property: level})
# property names:  meat fish shellfish egg dairy honey gelatin pork alcohol gluten og root mushroom ferment
#                  nuts peanut sesame soy mustard ghee ; levels: "no" definite, "maybe", "label"
R = []
def rule(pat, **props):
    R.append((re.compile(pat), props))

# animal flesh
rule(r"\b(chicken|mutton|lamb|goat|beef|veal|turkey|duck|keema|mince|steak|ribs?|wings?|oxtail|ox tail|tripe|offal|tongue|gizzards?|trotters?|ham hock|nduja|mortadella|bresaola|pastrami|jerky|brisket|goat|gosht|murgh|liver|brain|bone marrow|venison|rabbit|meat|paya|nihari|salami|pepperoni|meatballs?|meatloaf)\b", meat="no")
rule(r"\b(pork|bacon|ham|pancetta|prosciutto|lard|gammon|chorizo|sausages?|hot dogs?|spam|salami|pepperoni|carnitas|guanciale|trotters?|speck)\b", meat="no", pork="no")
rule(r"\b(fish|salmon|tuna|cod|haddock|hilsa|rohu|bhetki|pomfret|sardines?|anchov(y|ies)|mackerel|trout|tilapia|sea ?bass|bass|snapper|halibut|basa|surmai|bombil|bombay duck|fillets? of|katla|kingfish|swordfish|herring|whitebait|bonito|katsuobushi)\b", fish="no")
rule(r"\b(dashi)\b", fish="maybe")
rule(r"\b(kebabs?|kababs?|seekh|tikka|cutlets?|nuggets?|burgers?)\b", meat="maybe")
rule(r"\b(fish sauce|fishsauce|worcestershire|worcester|anchovy paste|nam pla|xo sauce)\b", fish="no")
rule(r"\b(oyster sauce|shrimp paste|belacan|terasi|kapi|prawn paste|prawn crackers?|krupuk|shrimp crackers?)\b", shellfish="no")
rule(r"\b(prawns?|shrimps?|crab|lobster|squid|calamari|octopus|clams?|mussels?|oysters?|scallops?|cuttlefish|crayfish|langoustine|cockles?|whelk|seafood)\b", shellfish="no")
rule(r"\b(fishcakeitem|codfish|cod fish|saltfish|salt fish|salt cod|bacalao|bacalhau|bulljaw|kippers?|smoked haddock|jellied eels?|ikan|nam pla)\b", fish="no")
rule(r"\b(crabcakeitem|crawfish|crawdads?|dried shrimps?|sea urchin|abalone|conch|krill)\b", shellfish="no")
rule(r"\b(eels?|catfish|shark|ray|skate|monkfish|sturgeon|caviar)\b", fish="no", nonkoshfish="no")
# eggs
rule(r"\b(eggs?|egg yolks?|egg whites?|yolks?|omelette|omelet|scrambled|poached|frittata|mayonnaise|mayo|aioli|meringue|hollandaise|bhurji|anda|quail)\b", egg="no")
rule(r"\b(pasta|spaghetti|noodles?|fresh pasta|tagliatelle|fettuccine|lasagn?e|ramen|udon)\b", egg="label")  # fresh/egg noodles are common
rule(r"\b(custard)\b", egg="maybe")
rule(r"\b(brioche|challah|pavlova|souffle|mousse|cake|sponge|crepes?|pancakes?|waffles?|french toast|choux|eclair|tiramisu)\b", egg="maybe")
# dairy
rule(r"\b(milk|whole milk|skimmed milk|full fat milk|dahi|curd|yogh?urt|greek yogh?urt|hung curd|buttermilk|chaas|lassi|raita|cream|double cream|single cream|heavy cream|whipping cream|sour cream|malai|creme fraiche|mascarpone|ricotta|paneer|chenna|chhena|cottage cheese|khoya|mawa|rabri|rabdi|condensed milk|evaporated milk|milk powder|whey|casein|ice ?cream|kulfi|butter|unsalted butter|salted butter|melted butter|makhan|cheese|cheddar|mozzarella|parmesan|parmigiano|pecorino|feta|halloumi|gruyere|gouda|brie|camembert|emmental|swiss cheese|cream cheese|processed cheese|queso|burrata|provolone|stilton|gorgonzola|blue cheese|dulce de leche|milkchocolate|white chocolate|dairy)\b", dairy="no")
rule(r"\b(ghee|desi ghee|clarified butter|butter ghee)\b", ghee="no")
rule(r"\b(chocolate|dark chocolate|chocolate chips?|cocoa powder|cocoa|bread|buns?|pav|naan|kulcha|bhatura|brioche|rolls?|loaf|toast|baguette|croissant|pastry|puff pastry|shortcrust|pizza dough|dough|biscuits?|cookies?|cake|sponge|tortilla|wraps?|crackers?|caramel|toffee|pudding|sweet|mithai|halwa|burfi|barfi|ladoo|laddu|gulab jamun|jalebi|rasmalai|rasgulla|kheer|payasam|firni|custard powder|instant mash|mashed potato|pesto|ranch|alfredo|bechamel|white sauce|korma|makhani|butter chicken|tikka masala|paneer)\b", dairy="maybe")
rule(r"\b(parmesan|parmigiano|pecorino|gruyere|emmental|stilton|gorgonzola|brie|camembert|cheddar|mozzarella|feta|halloumi|cheese)\b", rennet="maybe")
rule(r"\bhoney|clear honey|shahad|madhu|bee pollen|royal jelly\b", honey="no")
rule(r"\b(gelatin|gelatine|marshmallows?|jelly|jell o|aspic|isinglass|lard|suet|tallow|dripping|bone broth|bone stock)\b", gelatin="maybe")
rule(r"\b(chicken stock|beef stock|meat stock|fish stock|bone broth|bouillon|stock cubes?|stock|broth|consomme)\b", stock="label")
rule(r"\b(chicken stock|beef stock|lamb stock|meat stock|chicken broth|beef broth|chicken stock cube|beef stock cube)\b", meat="no")
rule(r"\b(fish stock|fish broth)\b", fish="no")
# alcohol
rule(r"\b(wine|red wine|white wine|dry white wine|rice wine|shaoxing|sherry|dry sherry|port|marsala|vermouth|brandy|cognac|rum|whisky|whiskey|bourbon|vodka|gin|tequila|beer|lager|ale|stout|cider|sake|mirin|liqueur|kahlua|amaretto|champagne|prosecco|aperol|baileys|grand marnier|cointreau|calvados|madeira|marsala)\b", alcohol="no")
rule(r"\b(vanilla extract|almond extract|vanilla essence|vanilla|rum essence|essence|extract|kewra|rose water|rosewater|orange blossom water)\b", alcoholtrace="label")
rule(r"\b(red wine vinegar|white wine vinegar|balsamic|balsamic vinegar|sherry vinegar|wine vinegar|malt vinegar|vinegar|apple cider vinegar|rice vinegar)\b", vinegar="label")
# gluten
rule(r"\b(wheat|atta|whole wheat|maida|plain flour|all ?purpose flour|self raising flour|self rising flour|bread flour|strong flour|flour|dalia|daliya|broken wheat|bulgur|bulgar|couscous|seitan|barley|rye|spelt|farro|freekeh|kamut|triticale|semolina|suji|sooji|rava|rawa|vermicelli|seviyan|sewai)\b", gluten="no")
rule(r"\b(bread|breadcrumbs?|bread crumbs?|panko|pita|pitta|naan|roti|chapat[ti]|chapati|phulka|paratha|parantha|puri|poori|bhatura|kulcha|thepla|pav|bun|buns|bagel|baguette|toast|croissant|ciabatta|focaccia|sourdough|brioche|crouton|bao|dumpling wrappers?|spring roll wrappers?|samosa pastry|filo|phyllo|puff pastry|shortcrust|pastry|pizza dough|pizza base|dough|biscuits?|digestive|cookies?|crackers?|cake|sponge|pancakes?|waffles?|pasta|spaghetti|macaroni|penne|lasagn?e|fusilli|tagliatelle|linguine|fettuccine|rigatoni|orzo|ravioli|tortellini|cannelloni|noodles?|ramen|udon|soba|chow mein|hakka noodles|maggi|malt|malted|beer|lager|ale|stout|teriyaki|soy sauce|soysauce|soya sauce|dark soy|light soy|beer batter|tempura|sev bhujia)\b", gluten="no")
rule(r"\b(noodles?|vermicelli|sev|tortilla|wrappers?|gnocchi|dumplings?|momos?|wontons?|samosas?|kachori|spring rolls?|croquettes?|cutlets?|nuggets?|burger|sandwich|bun)\b", gluten="maybe")
rule(r"\b(tefflour|injera|flatbread|batter|hoisin|wraps?)\b", gluten="maybe")
rule(r"\b(oats?|rolled oats|oatmeal|porridge|muesli|granola|cornflakes|cereal)\b", gluten="label")
rule(r"\b(hing|asafoetida|asafetida|heeng|stock cubes?|stock|bouillon|miso|gochujang|worcestershire|oyster sauce|baking powder|curry powder|sausages?|seasoning|spice mix|soup powder|gravy mix|instant|ready mix|custard powder|licorice|liquorice|malt vinegar)\b", gluten="label")
# onion / garlic
rule(r"\b(onions?|red onions?|spring onions?|springonion|scallions?|shallots?|leeks?|chives?|pyaaz|pyaz|kanda|onion powder|onion paste|fried onions?|birista|garlic|garlic cloves?|minced garlic|garlic paste|garlic powder|lehsun|lasun|ginger garlic|ginger garlic paste|asafoetida garlic|wild garlic|ramps)\b", og="no")
rule(r"\b(stock cubes?|stock|bouillon|curry powder|garam masala|pav bhaji masala|chole masala|sambar powder|biryani masala|meat masala|chicken masala|tikka masala|ready masala|seasoning|spice mix|gochujang|kimchi|hoisin|teriyaki|worcestershire|ketchup|salsa|tomato sauce|pesto|bbq sauce|sauce)\b", og="label")
# Jain: root veg, mushrooms, ferment
rule(r"\b(potato|potatoes|aloo|sweet potato|shakarkand|carrots?|gajar|radish|mooli|daikon|beetroot|beets?|chukandar|turnips?|shalgam|ginger|adrak|ginger paste|turmeric root|fresh turmeric|yam|suran|jimikand|colocasia|arbi|taro|cassava|tapioca root|parsnips?|celeriac|swede|rutabaga|jerusalem artichoke|salsify|lotus root|kanda|pyaaz|onions?|garlic)\b", root="no")
rule(r"\b(dry ginger|ground ginger|ginger powder|saunth|sonth|dried ginger)\b", gingerdry="maybe")
rule(r"\b(mushrooms?|button mushroom|shiitake|oyster mushroom|portobello|cremini|truffle|khumb|yeast|dosa batter|idli batter|batter|fermented|kimchi|sauerkraut|miso|tempeh|natto|vinegar|wine|beer|sake|mirin|pickles?|achaar|bhatura|nan|naan|kulcha|bread|pav|bun|pizza dough)\b", ferment="maybe")
rule(r"\b(mushrooms?|shiitake|portobello|cremini|truffle|khumb)\b", mushroom="maybe")
rule(r"\b(honey|shahad|clear honey)\b", jainhoney="maybe")
# allergens
rule(r"\b(almonds?|badam|cashews?|cashew nuts?|kaju|pistachios?|pista|walnuts?|akhrot|pecans?|hazelnuts?|macadamia|brazil nuts?|chestnuts?|pinenut|pine nuts?|marzipan|nutella|praline|mixed nuts|nuts|almond extract|almond flour|almond meal|frangipane|baklava|treenutspread)\b", nuts="no")
rule(r"\b(peanuts?|moongphali|groundnuts?|peanutspread|peanut oil|groundnut oil|satay)\b", peanut="no")
rule(r"\b(seedspread)\b", sesame="no")
rule(r"\b(sesame|til|tahini|sesame oil|sesame seed oil|sesame seeds?|gingelly|hummus|sesamehalva|gomashio|za atar|zaatar|dukkah|benne|bagel)\b", sesame="no")
rule(r"\b(soy|soya|soy sauce|soysauce|soya sauce|tofu|tempeh|edamame|miso|soya chunks?|nutrela|soy milk|plant_milk|natto|teriyaki|hoisin|gochujang|beancurd|soymilk|soybean|soyabean|lecithin|textured vegetable protein|tvp)\b", soy="no")
rule(r"\b(mustard|dijon|mustard seeds?|mustardseedoil|sarson|rai|kasundi|mustard powder|wholegrain mustard|english mustard|american mustard|mustard greens)\b", mustard="no")
rule(r"\b(mustard oil)\b", mustard="no")
# halal-relevant
rule(r"\b(pork|bacon|ham|pancetta|prosciutto|lard|gammon|chorizo|sausages?|salami|pepperoni|guanciale|speck|spam|hot dogs?)\b", pork="no")
rule(r"\b(gelatin|gelatine|marshmallows?|isinglass|aspic)\b", gelatin="no")
rule(r"\bsausages?\b", pork="maybe")
# non-kosher
rule(r"\b(shellfish|prawns?|shrimps?|crab|lobster|squid|calamari|octopus|clams?|mussels?|oysters?|scallops?|cuttlefish|crayfish|langoustine)\b", shellfishk="no")
rule(r"\b(rabbit|hare|camel|horse|boar|venison)\b", nonkoshmeat="maybe")
rule(r"\b(grape juice|wine|red wine|white wine|brandy|cognac|port|sherry|marsala|vermouth|champagne|prosecco)\b", grape="maybe")
rule(r"\b(vinegar|wine vinegar|balsamic)\b", grape="label")

# steps text is noisy ("serve with butter"); only these ingredient words are taken from method text
STEP_WORDS = re.compile(r"\b(honey|egg|eggs|butter|ghee|cream|milk|curd|yogh?urt|cheese|paneer|onion|onions|garlic|ginger|potato|wine|beer|rum|bacon|chicken|prawns?|fish|soy sauce|flour|maida|atta|bread|breadcrumbs|noodles|pasta|gelatin|mayonnaise|worcestershire|fish sauce|oyster sauce|peanuts?|cashews?|almonds?|walnuts?|sesame|tahini|mustard)\b")

ALL_ALLERGENS = ["dairy", "gluten", "egg", "soy", "nuts", "sesame", "peanut", "fish", "mustard", "shellfish"]
LV = {"no": 3, "maybe": 2, "label": 1}


def scan_text(text, found, src, alt=False):
    t = norm(text)
    for rx, props in R:
        m = rx.search(t)
        if m:
            for k, lv in props.items():
                if src == "name" and k == "gluten" and lv == "no":
                    lv = "maybe"   # a dish NAME (Rice Noodle Soup, Pancakes) is only a pointer; the ingredient list decides
                if alt and lv == "no":
                    if k in ("meat", "fish", "shellfish", "egg"):
                        found.setdefault("animalalt", []).append(("maybe", m.group(0).strip(), src))
                    lv = "maybe"   # "milk or water", "tofu/prawn": the dish can be made either way
                found.setdefault(k, []).append((lv, m.group(0).strip(), src))
    return found


def strongest(found, key, sources=("ing", "name")):
    best = None
    for lv, word, src in found.get(key, []):
        if src not in sources:
            continue
        if best is None or LV[lv] > LV[best[0]]:
            best = (lv, word, src)
    return best


def analyse(r):
    found = {}
    for ing in r.get("ingredients", []):
        nm = ing.get("name", "")
        scan_text(nm + " | " + ing.get("key", ""), found, "ing", alt=bool(re.search(r"\bor\b|/|\boptional\b|\bif you like\b|\bto serve\b", nm.lower())))
    scan_text(r.get("name", ""), found, "name")
    # method text: only a pointer (maybe), never decisive on its own
    step_text = " ".join(r.get("steps", []))
    nstep = norm(step_text)
    in_steps = set(m.group(0) for m in STEP_WORDS.finditer(nstep))
    listed_words = norm(" ".join(i.get("name", "") + " " + i.get("key", "") for i in r.get("ingredients", [])) + " " + r.get("name", ""))
    only_in_steps = sorted(w for w in in_steps if not re.search(r"\b" + re.escape(w) + r"\b", listed_words)
                           and not re.search(r"\b" + re.escape(w.rstrip("s")) + r"s?\b", listed_words))
    step_found = {}
    for w in only_in_steps:
        scan_text(w, step_found, "step")
    for k, v in step_found.items():
        found.setdefault(k, []).extend(v)

    def has(key, level=None, sources=("ing", "name")):
        b = strongest(found, key, sources)
        return b and (level is None or b[0] == level)

    def word(key, sources=("ing", "name")):
        b = strongest(found, key, sources)
        return b[1] if b else ""

    def stepword(key):
        b = strongest(found, key, ("step",))
        return b[1] if b else ""

    out = {"why": {}, "alerts": [], "found": found, "only_in_steps": only_in_steps}
    A = out["alerts"]

    def add(attr, level, why):
        out["why"].setdefault(attr, []).append(why)
        if level != "yes":
            A.append("%s:%s:%s" % (attr, level, why))

    # ---- animal / diet class
    animal_flesh = has("meat", "no") or has("fish", "no") or has("shellfish", "no")
    egg_def = has("egg", "no")
    if animal_flesh:
        diet = "nonveg"
    elif egg_def:
        diet = "egg"
    else:
        diet = "veg"
    out["diet"] = diet
    out["diet_maybe"] = [b_[1] for b_ in (strongest(found, k_) for k_ in ("fish", "meat", "shellfish")) if b_ and b_[0] == "maybe"]
    for k_ in ("fish","meat","shellfish"):
        b_ = strongest(found, k_)
        if b_ and b_[0]=="maybe":
            A.append("diet:maybe:%s is usually animal-based, confirm a vegetarian version" % b_[1])
    out["diet_why"] = word("meat") or word("fish") or word("shellfish") or word("egg")

    # ---- vegan
    vegan_no = [w for k in ("meat", "fish", "shellfish", "egg", "honey") for w in [word(k)] if has(k, "no")]
    dairy_no = has("dairy", "no") or has("ghee", "no")
    if dairy_no:
        vegan_no.append(word("dairy") or word("ghee"))
    vegan = not vegan_no
    vegan_maybe = []
    if vegan:
        for k in ("gelatin", "rennet", "egg", "dairy", "stock"):
            b = strongest(found, k)
            if b and b[0] in ("maybe", "label"):
                vegan_maybe.append("%s (%s)" % (b[1], k))
    out["vegan"] = vegan
    out["vegan_why"] = ", ".join(vegan_no)
    out["vegan_maybe"] = vegan_maybe

    # ---- lactose
    lact_no = has("dairy", "no")
    if lact_no:
        gf_lact = "no"; why = word("dairy")
    elif has("ghee", "no"):
        gf_lact = "label"; why = "ghee is nearly lactose-free but not guaranteed"
    elif strongest(found, "dairy") and strongest(found, "dairy")[0] == "maybe":
        gf_lact = "maybe"; why = "%s can contain milk/butter" % word("dairy")
    elif vegan_maybe and any("dairy" in x or "rennet" in x for x in vegan_maybe):
        gf_lact = "maybe"; why = ", ".join(vegan_maybe)
    else:
        gf_lact = "yes"; why = ""
    if stepword("dairy") and gf_lact == "yes":
        gf_lact = "maybe"; why = "method mentions %s but the ingredient list does not" % stepword("dairy")
    out["lactoseFree"] = gf_lact
    if gf_lact != "yes":
        add("lactose", gf_lact, why)

    # ---- gluten
    g = strongest(found, "gluten")
    if g and g[0] == "no":
        gl = "no"; gw = g[1]
    elif g and g[0] == "maybe":
        gl = "maybe"; gw = "%s (wheat or not, depends on how it is made)" % g[1]
    elif g and g[0] == "label":
        gl = "label"; gw = "%s (can carry wheat, read the pack)" % g[1]
    else:
        gl = "yes"; gw = ""
    sg = strongest(found, "gluten", ("step",))
    if gl == "yes" and sg:
        gl = "maybe"; gw = "method mentions %s but the ingredient list does not" % sg[1]
    out["gf"] = gl
    if gl != "yes":
        add("gluten", gl, gw)

    # ---- halal
    if has("pork", "no") or has("gelatin", "no"):
        hl = "no"; hw = word("pork") or word("gelatin")
    elif has("alcohol", "no"):
        hl = "no"; hw = word("alcohol")
    elif animal_flesh and (has("meat", "no")):
        hl = "maybe"; hw = "%s must be halal-slaughtered" % word("meat")
    elif has("pork", "maybe"):
        hl = "maybe"; hw = "%s may be pork" % word("pork")
    elif has("gelatin", "maybe") or has("rennet", "maybe"):
        hl = "label"; hw = "%s may use animal gelatin/rennet" % (word("gelatin") or word("rennet"))
    elif has("alcoholtrace", "label") or has("vinegar", "label") and "wine" in word("vinegar"):
        hl = "label"; hw = "%s may contain alcohol" % (word("alcoholtrace") or word("vinegar"))
    elif has("stock", "label") and not vegan:
        hl = "label"; hw = "stock/cube may be non-halal"
    else:
        hl = "yes"; hw = ""
    out["halal"] = hl
    if hl != "yes":
        add("halal", hl, hw)

    # ---- kosher
    meat_dairy = (has("meat", "no") and (dairy_no and not has("ghee", "no") or has("ghee", "no") or has("dairy", "no")))
    if has("pork", "no") or has("shellfishk", "no") or has("shellfish", "no"):
        ko = "no"; kw = word("pork") or word("shellfish")
    elif has("nonkoshfish", "no"):
        ko = "no"; kw = word("nonkoshfish") + " is not a kosher fish"
    elif has("gelatin", "no"):
        ko = "no"; kw = word("gelatin")
    elif has("meat", "no") and has("dairy", "no"):
        ko = "no"; kw = "meat (%s) cooked with dairy (%s)" % (word("meat"), word("dairy"))
    elif has("meat", "no") and has("ghee", "no"):
        ko = "no"; kw = "meat with ghee (dairy)"
    elif has("meat", "no"):
        ko = "maybe"; kw = "%s must be kosher-slaughtered" % word("meat")
    elif has("fish", "no") and has("dairy", "no"):
        ko = "maybe"; kw = "fish with dairy: fine for many, avoided by some"
    elif has("alcohol", "no") or has("grape", "maybe"):
        ko = "maybe"; kw = "%s needs kosher certification" % (word("alcohol") or word("grape"))
    elif has("gelatin", "maybe") or has("rennet", "maybe"):
        ko = "label"; kw = "%s may be non-kosher gelatin/rennet" % (word("gelatin") or word("rennet"))
    elif has("grape", "label") or has("alcoholtrace", "label"):
        ko = "label"; kw = "%s may be grape/alcohol based" % (word("grape") or word("alcoholtrace"))
    else:
        ko = "yes"; kw = ""
    out["kosher"] = ko
    if ko != "yes":
        add("kosher", ko, kw)

    # ---- jain (existing app meaning: no root veg; plus no meat/egg/fish/honey/mushroom)
    jain_no = []
    if animal_flesh or egg_def:
        jain_no.append(word("meat") or word("fish") or word("shellfish") or word("egg"))
    if has("root", "no"):
        jain_no.append(word("root"))
    if has("og", "no"):
        jain_no.append(word("og"))
    jain = not jain_no
    jain_maybe = []
    if jain:
        for k_, why_ in (("mushroom","mushrooms are avoided by many Jains"),("jainhoney","honey is avoided by Jains"),("gingerdry","dry ginger: some Jains accept it, some do not")):
            b_ = strongest(found, k_)
            if b_: jain_maybe.append("%s (%s)" % (b_[1], why_))
        fm = strongest(found, "ferment")
        if fm:
            jain_maybe.append("%s (fermented or yeast product)" % fm[1])
        if has("og", "label"):
            jain_maybe.append("%s (ready blends often carry onion/garlic)" % word("og"))
        if stepword("og"):
            jain_maybe.append("method mentions %s, ingredient list does not" % stepword("og"))
        if stepword("root"):
            jain_maybe.append("method mentions %s, ingredient list does not" % stepword("root"))
    out["jain"] = jain
    out["jain_why"] = ", ".join(sorted(set(jain_no)))
    out["jain_maybe"] = jain_maybe
    if jain_maybe:
        for x in jain_maybe:
            A.append("jain:maybe:" + x)
        out["why"].setdefault("jain", []).extend(jain_maybe)

    # ---- no onion / garlic
    og_no = has("og", "no")
    noog = not og_no
    noog_maybe = []
    if noog:
        if has("og", "label"):
            noog_maybe.append("%s (ready blends often carry onion/garlic)" % word("og"))
        if stepword("og"):
            noog_maybe.append("method mentions %s, ingredient list does not" % stepword("og"))
    out["noOG"] = noog
    out["noOG_why"] = word("og") if og_no else ""
    out["noOG_maybe"] = noog_maybe
    for x in noog_maybe:
        A.append("onion-garlic:maybe:" + x)

    # ---- allergens (the ten groups)
    comp = set()
    amap = {"dairy": "dairy", "gluten": "gluten", "egg": "egg", "soy": "soy", "nuts": "nuts", "sesame": "sesame",
            "peanut": "peanut", "fish": "fish", "mustard": "mustard", "shellfish": "shellfish"}
    allerg_why = {}
    for a, k in amap.items():
        b = strongest(found, k)
        if a == "dairy":
            b = b if (b and b[0] == "no") else (strongest(found, "ghee") if has("ghee", "no") else None)
        if b and b[0] == "no":
            comp.add(a); allerg_why[a] = b[1]
    if gl == "no":
        comp.add("gluten"); allerg_why.setdefault("gluten", gw)
    out["allergens"] = sorted(comp)
    out["allergen_why"] = allerg_why
    # "may contain" alerts for the allergens the stored list would miss
    may = []
    if gl in ("maybe", "label"):
        may.append("gluten")
    if gf_lact in ("maybe", "label"):
        may.append("dairy")
    for k, a in (("egg", "egg"),):
        b = strongest(found, k)
        if b and b[0] in ("maybe", "label") and a not in comp:
            may.append(a)
    out["allergens_may"] = sorted(set(may))
    for a in out["allergens_may"]:
        A.append("allergen:%s:%s" % ("maybe", "may contain " + a))
    # de-dup alerts, keep order
    seen = set(); A2 = []
    for x in A:
        if x not in seen:
            seen.add(x); A2.append(x)
    out["alerts"] = A2
    return out


def main():
    path = sys.argv[1]
    apply = "--apply" in sys.argv
    repdir = sys.argv[sys.argv.index("--report") + 1] if "--report" in sys.argv else None
    cat = json.load(open(path))
    recs = cat["recipes"]
    fixes = []       # stored value was LESS strict than the ingredients prove: made safer
    relaxed = []     # stored stricter than the ingredients, but only because of a false-friend word (coconut milk, egg plant): corrected, listed
    review = []      # stored value is stricter than the ingredients support: a person looks, nothing changes
    alerts_n = collections.Counter()
    stats = collections.Counter()
    for r in recs:
        a = analyse(r)
        rid = r["id"]
        # ---- safety fixes (only ever toward stricter)
        order = {"veg": 0, "egg": 1, "nonveg": 2}
        if order[a["diet"]] > order.get(r.get("diet", "veg"), 0):
            fixes.append((rid, r["name"], "diet", r.get("diet"), a["diet"], a["diet_why"]))
            r["diet"] = a["diet"]
        elif order[a["diet"]] < order.get(r.get("diet"), 0):
            raw = " ".join(i.get("name", "") for i in r.get("ingredients", [])).lower() + " " + " ".join(r.get("steps", [])).lower() + " " + r["name"].lower()
            raw2 = re.sub(r"egg ?plants?", "aubergine", raw)
            false_friend = re.search(r"egg ?plants?", raw) and not re.search(r"\beggs?\b|\byolks?\b|mayo", raw2)
            if r.get("diet") == "egg" and a["diet"] == "veg" and false_friend:
                review.append((rid, r["name"], "diet", "egg", "veg", "only 'egg plant' (aubergine) found, no egg: stored value left strict, a person confirms"))
            elif a["found"].get("animalalt") or a["diet_maybe"]:
                pass   # stored stricter on purpose: the list gives an animal alternative ("beef/chicken", "tofu/prawn")
            else:
                review.append((rid, r["name"], "diet", r.get("diet"), a["diet"], "no animal ingredient found in the list"))
        if r.get("vegan") and not a["vegan"]:
            fixes.append((rid, r["name"], "vegan", True, False, a["vegan_why"])); r["vegan"] = False
        elif (not r.get("vegan")) and a["vegan"] and not a["vegan_maybe"]:
            raw = " ".join(i.get("name", "") for i in r.get("ingredients", [])).lower() + " " + r["name"].lower()
            ff = re.search(r"coconut (milk|cream)|egg ?plant|butternut|(almond|soy|soya|oat|cashew|rice) milk|nut butter|peanut butter", raw)
            if ff and not a["found"].get("animalalt") and not a["found"].get("dairy") and not a["found"].get("egg"):
                review.append((rid, r["name"], "vegan", False, True, "only a plant 'milk/cream/butter' or egg plant found (" + ff.group(0) + "): stored value left strict, a person confirms"))
            else:
                review.append((rid, r["name"], "vegan", False, True, "no animal ingredient found"))
        if r.get("jain") and not a["jain"]:
            fixes.append((rid, r["name"], "jain", True, False, a["jain_why"])); r["jain"] = False
        elif (not r.get("jain")) and a["jain"] and not a["jain_maybe"]:
            review.append((rid, r["name"], "jain", False, True, "no root veg / onion / garlic / animal ingredient found"))
        if r.get("noOG") and not a["noOG"]:
            fixes.append((rid, r["name"], "noOG", True, False, a["noOG_why"])); r["noOG"] = False
        elif (not r.get("noOG")) and a["noOG"] and not a["noOG_maybe"]:
            review.append((rid, r["name"], "noOG", False, True, "no onion/garlic ingredient found"))
        stored = set(r.get("allergens", []))
        missing = sorted(set(a["allergens"]) - stored)
        extra = sorted(stored - set(a["allergens"]))
        if missing:
            fixes.append((rid, r["name"], "allergens", sorted(stored), sorted(stored | set(missing)),
                          ", ".join("%s (%s)" % (m, a["allergen_why"].get(m, "")) for m in missing)))
            r["allergens"] = sorted(stored | set(missing))
        if extra:
            review.append((rid, r["name"], "allergens", sorted(stored), a["allergens"], "listed but not found in ingredients: " + ", ".join(extra)))
        # ---- the stored allergen tokens must agree with vegan / diet (the apps refuse a feed where they do not)
        toks = set(r.get("allergens", []))
        if r.get("vegan") and toks & {"dairy", "egg", "fish", "shellfish"}:
            fixes.append((rid, r["name"], "vegan", True, False, "allergen list has " + ", ".join(sorted(toks & {"dairy", "egg", "fish", "shellfish"}))))
            r["vegan"] = False
        need = "nonveg" if toks & {"fish", "shellfish"} else ("egg" if "egg" in toks else "veg")
        if order[need] > order.get(r.get("diet", "veg"), 0):
            fixes.append((rid, r["name"], "diet", r.get("diet"), need, "allergen list has " + ", ".join(sorted(toks & {"fish", "shellfish", "egg"}))))
            r["diet"] = need
        # ---- new fields, merged with whatever the catalogue already carries.
        # Live format (apps read this): gf / lactoseFree / halal / kosher = yes | if | no,
        # dietWhy = {field: [reasons]}. Merge only ever goes stricter, never relaxes.
        ORD = {"yes": 0, "if": 1, "no": 2}
        MAP = {"yes": "yes", "maybe": "if", "label": "if", "if": "if", "no": "no"}
        # dietWhy belongs to diet_check.py and the apps turn its "ingredient (needs X)" lines
        # into the "Use X" note, so it is never touched here. This gate's own reasons, which are
        # free text, go to gateWhy.
        if not isinstance(r.get("dietWhy"), dict):
            r["dietWhy"] = {}
        gate_why = {}
        for attr, wkey in (("gluten", "gf"), ("lactose", "lactose"), ("halal", "halal"), ("kosher", "kosher")):
            ws = list(dict.fromkeys(a["why"].get(attr, [])))
            if ws:
                gate_why[wkey] = ws
        for fld, src in (("gf", "gf"), ("lactoseFree", "lactoseFree"), ("halal", "halal"), ("kosher", "kosher")):
            mine = MAP[a[src]]
            prev = MAP.get(r.get(fld), "yes") if fld in r else "yes"
            r[fld] = mine if ORD[mine] >= ORD[prev] else prev
        r["gateWhy"] = gate_why
        r["checkAlerts"] = a["alerts"]
        r["checkedBy"] = "gate-v1"
        for al in a["alerts"]:
            alerts_n[al.split(":")[0] + ":" + al.split(":")[1]] += 1
        for k in ("gf", "lactoseFree", "halal", "kosher"):
            stats["%s=%s" % (k, r[k])] += 1
    if apply:
        cat["recipes"] = recs
        tmp = path + ".new"
        json.dump(cat, open(tmp, "w"), ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    if repdir:
        os.makedirs(repdir, exist_ok=True)
        json.dump({"fixes": fixes, "relaxed": relaxed, "review": review}, open(os.path.join(repdir, "gate_fixes_review.json"), "w"), ensure_ascii=False, indent=1)
        # alert queue = every dish with any maybe/label/no for the four new attributes, grouped
        with open(os.path.join(repdir, "gate_report.md"), "w") as f:
            f.write("# Khao recipe gate: %d dishes checked\n\n" % len(recs))
            f.write("## Totals\n")
            for k, v in sorted(stats.items()):
                f.write("- %s: %d\n" % (k, v))
            f.write("\n## Stored values made safer (%d)\n" % len(fixes))
            for x in fixes:
                f.write("- %s %s | %s: %s -> %s | %s\n" % x)
            f.write("\n## Over-strict stored values corrected (%d), false-friend words only\n" % len(relaxed))
            for x in relaxed:
                f.write("- %s %s | %s: %s -> %s | %s\n" % x)
            f.write("\n## Needs a person to look (%d)\n" % len(review))
            for x in review:
                f.write("- %s %s | %s: stored %s, ingredients say %s | %s\n" % x)
    print("dishes", len(recs), "fixes", len(fixes), "review", len(review))
    for k, v in sorted(stats.items()):
        print(k, v)
    print("fix kinds", collections.Counter(x[2] for x in fixes))
    print("review kinds", collections.Counter(x[2] for x in review))


if __name__ == "__main__":
    main()
