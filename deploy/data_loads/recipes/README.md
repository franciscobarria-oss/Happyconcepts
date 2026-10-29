# Recipe load from staging (one-off, idempotent)

1. On staging: `export_recipes.py` writes `staging_recipes.json` (read-only).
2. Build `code_map.json` (`{"map": {old_code: new_code|"SKIP"}, "names": {old_code: old_name}}`) from the
   item-matching choices and `new_item_codes.json`.
3. On hcl-erp: `import_recipes.py` with `dry_run=True`, check `recipe_load_review.csv`, then `dry_run=False`.

Recipes with an unmatched ingredient or a unit that doesn't fit the ingredient are not loaded; they are listed in the review.
