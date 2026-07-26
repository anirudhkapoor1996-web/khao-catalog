# Khao dish catalogue

The dish list the Khao iOS app reads. `catalog.json` is data only — no code.

Shape: `{"format": 1, "version": N, "recipes": [...]}`

The app installs a file only when `version` is higher than the one it already has, so bump `version` on every change or nothing happens. It also refuses any file that is smaller than the list built into the app, or that has duplicate ids, blank names, or no fasting / vegetarian / breakfast dishes. Any failure leaves the app on the dishes it already had.
