# Khao diet check - catalogue v45 (18 Nov 2026)

Every ingredient of all 2240 dishes was read against written rules (diet_check.py). Tags were not trusted.

The checker only makes dishes stricter. It never removes an allergen or turns Jain on by itself.

## Result

| Check | yes | only with a swap ("if") | no |
|---|---|---|---|
| Gluten-free | 947 | 303 | 990 |
| Halal | 1252 | 689 | 299 |
| Kosher | 1153 | 555 | 532 |

"if" examples: halal or kosher meat, gluten-free hing, kosher wine, certified cheese or gelatin.

- Missing allergens added: 239 dishes-allergen pairs
- Jain turned off: 39 dishes that an ingredient breaks
- Marked veg or vegan but an ingredient says otherwise: 24 (listed below for a person to rule; not changed)

## Jain turned off

- Kerala Avial: mixed veg (drumstick,carrot) (root, bulb or mushroom)
- Vattayappam: dry yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Kashmiri Bakarkhani: dry yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Farali Dhokla: green chilli-ginger paste (root, bulb or mushroom)
- Aubergine & hummus grills: aubergine (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Aubergine couscous salad: aubergine (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Bajan Salt Bread Recipe: yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Baked Yuca Fries: yuca (root, bulb or mushroom)
- Cassava bread: cassava flour (root, bulb or mushroom)
- Cassava Cake: cassava (root, bulb or mushroom)
- Chinon Apple Tarts: red wine jelly (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Chocolate Avocado Mousse: honey (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Danish Rye Bread: dark beer (honey, yeast, alcohol, gelatin or many-seeded vegetable); yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Dominica mastiff bread: instant yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Dutch doughnuts: instant yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Griddled flatbreads: yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Honey Cookies: honey (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Hot Chocolate Fudge: miniature marshmallows (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Jam Roly-Poly: suet (meat, fish or egg); custard (meat, fish or egg)
- Layered mango custard: custard (meat, fish or egg)
- Madombi: Dumplings from Botswana: yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Magwinya: Doughnut Bites from Botswana: yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- No-Churn Rum Raisin Ice Cream: dark rum (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Peanut Butter Cheesecake: gelatine leafs (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Pear Tarte Tatin: brandy (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Pizza Express Margherita: yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Raspberry mousse: gelatine leafs (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Rocky Road Fudge: miniature marshmallows (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Rye bread: yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable); honey (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Spotted Dick: suet (meat, fish or egg); custard (meat, fish or egg)
- Strawberries Romanoff: grand marnier (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Syrian Bread: yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Traditional Dutch rice tart (rijstevlaai): yeast (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Breadfruit Tacos: codfish bulljaw (meat, fish or egg)
- plantain rolls: codfish bulljaw (meat, fish or egg)
- Spanish fig & almond balls: brandy (honey, yeast, alcohol, gelatin or many-seeded vegetable); clear honey (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Basic Sourdough Loaf: sourdough starter (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Hobbs House Sourdough Bread: sourdough starter (honey, yeast, alcohol, gelatin or many-seeded vegetable)
- Iru Puli Kuzhambu: brinjal, cubed (honey, yeast, alcohol, gelatin or many-seeded vegetable)

## Veg / vegan conflicts to rule on (not changed)

- Miso Soup (JPN-V-1-1-217): marked veg but has meat, fish or egg
- Miso Soup (JPN-V-1-1-217): marked vegan but has an animal product
- Fresh Spring Rolls (VIE-V-1-1-262): marked veg but has meat, fish or egg
- Fresh Spring Rolls (VIE-V-1-1-262): marked vegan but has an animal product
- Vegetable Tempura (JPN-V-1-2-001): marked veg but has meat, fish or egg
- Vegetable Tempura (JPN-V-1-2-001): marked vegan but has an animal product
- Udon Noodle Soup (JPN-V-1-2-002): marked veg but has meat, fish or egg
- Fruit Custard (IND-V-0-3-013): marked veg but has meat, fish or egg
- Radhaballabhi (IND-V-2-4-015): marked vegan but has an animal product
- Santula (ODI-V-1-1-001): marked vegan but has an animal product
- Agedashi Tofu (JPN-V-0-3-001): marked veg but has meat, fish or egg
- Gemista (GRK-V-0-2-001): marked veg but has meat, fish or egg
- Gemista (GRK-V-0-2-001): marked vegan but has an animal product
- Kenchinjiru (JPN-V-0-1-002): marked veg but has meat, fish or egg
- Barramundi with Moroccan spices (FND-V-BARRAMUNDIWITH): marked veg but has meat, fish or egg
- Barramundi with Moroccan spices (FND-V-BARRAMUNDIWITH): marked vegan but has an animal product
- Conch Stew (FND-V-CONCHSTEW): marked veg but has meat, fish or egg
- Conch Stew (FND-V-CONCHSTEW): marked vegan but has an animal product
- Frog Legs Recipe in Garlic Butter (FND-V-FROGLEGSRECIPE): marked veg but has meat, fish or egg
- Jam Roly-Poly (FND-V-JAMROLYPOLY): marked veg but has meat, fish or egg
- Layered mango custard (FND-V-LAYEREDMANGOCU): marked veg but has meat, fish or egg
- Mushroom & Chestnut Rotolo (FND-V-MUSHROOMCHESTN): marked veg but has meat, fish or egg
- Mushroom & Chestnut Rotolo (FND-V-MUSHROOMCHESTN): marked vegan but has an animal product
- Pilchard puttanesca (FND-V-PILCHARDPUTTAN): marked veg but has meat, fish or egg
- Spicy Arrabiata Penne (FND-V-SPICYARRABIATA): marked vegan but has an animal product
- Spotted Dick (FND-V-SPOTTEDDICK): marked veg but has meat, fish or egg
- Vegan Lasagna (FND-V-VEGANLASAGNA): marked veg but has meat, fish or egg
- Breadfruit Tacos (FND-V-BREADFRUITTACO): marked veg but has meat, fish or egg
- Breadfruit Tacos (FND-V-BREADFRUITTACO): marked vegan but has an animal product
- plantain rolls (FND-V-PLANTAINROLLS): marked veg but has meat, fish or egg
- plantain rolls (FND-V-PLANTAINROLLS): marked vegan but has an animal product
- Potato, Tomato and Basil Salad (FND-V-POTATOTOMATOAN-DE0D5): marked veg but has meat, fish or egg
- Potato, Tomato and Basil Salad (FND-V-POTATOTOMATOAN-DE0D5): marked vegan but has an animal product
- Hasselback Butternut Squash with Tofu and Bean Ricotta (FND-V-HASSELBACKBUTT-8DA9D): marked vegan but has an animal product
