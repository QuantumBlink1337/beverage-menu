# Ingredient Mapping via Grocy Userfields

## Context

Today the matcher (`app/controllers/crafted_drinks.py` `_build_response`) resolves a Notion
ingredient name to a Grocy product in three tiers: **explicit `IngredientMapping` row →
exact product name → product group**. The explicit mappings live in the app's own SQLite
table (`IngredientMapping`), edited only via the headless `/api/mappings` CRUD router — there
is no host UI, so it's the one piece of precious, hand-entered data on the prod volume.

Two problems are converging:
1. **No editing UI** for mappings (a long-standing open item).
2. The **strict-availability fix** (`available = all_matched_in_stock and not unmatched`) means
   any unresolved ingredient now *hides* a drink from guests — so pantry/garnish staples
   (ice, edible glitter, lemonade) must be resolvable too, or makeable drinks vanish.

**Grocy userfields** solve both. A userfield is a custom field Grocy lets you define on an
entity (here, `products`) and edit on the normal product page. Moving mappings there makes
Grocy the single source of truth, gives the host a real editing UI for free, and colocates
the mapping with the product (delete the product, the mapping goes too — no dangling refs).

**Decisions made:** retire `IngredientMapping` entirely; seed Grocy from existing rows with a
one-time migration script; mark staples with a per-product `always_available` checkbox.

**Key simplification this unlocks:** once mappings live in Grocy, the app's SQLite DB holds
*no* precious data — it becomes a pure cache of Grocy + Notion. So the schema migration is
just "delete `beverage.db` and let it rebuild," no `ALTER TABLE` needed. (Do this only
*after* the seed script has run and been verified.)

---

## Grocy userfield mechanics

- Define two userfields in Grocy UI (Manage → Userfields), entity **`products`**:
  - **`notion_aliases`** — type *text* (multiline). Newline- or comma-separated Notion
    ingredient names that map to this product.
  - **`always_available`** — type *checkbox*. Flags **truly-infinite** items only (ice, water)
    as always in-stock. **Not** for consumables you run out of — see the scoping note below.
- **Userfields are returned inline** on `GET /api/objects/products` (confirmed against the live
  instance): each product row carries a `userfields` object, e.g.
  `"userfields": { "notion_aliases": null }`. So there's **no N+1 fetch** — parse it off the
  product dict. An unset field comes back as `null`. Writing (for the seed script) is
  `PUT /api/userfields/products/{id}`.

### Host workflow: how mappings get created

A "mapping" = telling the system a Notion ingredient name corresponds to a Grocy product. You
remain responsible for these, but you create them **in Grocy's product page** (the
`notion_aliases` field) instead of the old headless API/DB. You only need an alias for names
that don't already auto-resolve, since the matcher tries three tiers:
1. **Exact product name** (Notion name == Grocy product name) — no alias needed.
2. **Product group** (Notion name == a Grocy group, e.g. "Bourbon") — no alias needed.
3. **Alias** — only for divergent names ("Ginger Beer" → "Bundaberg Ginger Beer").

So ongoing effort is just the mismatches. The seed script (Phase B) carries over everything
you've already mapped, and **host mode surfaces what still needs one** — an unresolved
ingredient shows as `unmatched` in the prep panel and hides the drink for guests, pointing you
to the alias to add. Escape hatch: rename the Notion ingredient to match a Grocy product/group
name exactly and tiers 1–2 handle it with zero aliases.

### Scoping `always_available` (important)

`always_available` makes the matcher treat a product as in-stock **regardless of real stock**.
That is correct only for things you never run out of and never track (ice, water). For
consumables — lemonade, juice, syrups — flagging them would show a drink as makeable when
you're actually out, misleading guests. **Those should instead be real Grocy products with
stock + a `notion_aliases` entry**, so the normal stock tier hides the drink when you run dry.
Rule of thumb: *flag → infinite/untracked; track as product → anything you can run out of.*

---

## Implementation

Rollout is ordered so prod's hand-entered mappings are never lost: **add readers + script →
seed Grocy → verify → remove `IngredientMapping`.**

### Phase A — Userfield plumbing + new matching

- **`app/models.py` `GrocyProduct`** — add `aliases: list[str] = []` and
  `always_available: bool = False`.
- **`app/db.py` `GrocyProduct`** — add `aliases = JSONListField()` and
  `always_available = BooleanField(default=False)`. `upsert_all` already passes `**data`, so
  no method change.
- **`app/grocy_client.py`** — populate the new fields in `parse_product` from the inline
  `userfields` object (no extra request):
  - `uf = raw.get("userfields") or {}` (defensive — `userfields` may be absent and individual
    values may be `null`, so a missing/undefined field degrades to `[]` / `False`, never a
    `KeyError`).
  - aliases = `uf.get("notion_aliases")` split on newline/comma, `strip`, drop empties (handle
    `None`); `always_available` = Grocy checkbox (`"1"`/`"0"`/`null`) → bool.
- **`app/controllers/crafted_drinks.py` `_build_response`** — two changes:
  - Build the alias map from products (reuse `_norm` for case/whitespace-insensitivity):
    `alias_map[_norm(alias)] = p.id` for each alias on each product. New precedence:
    **alias → exact product name → product group** (the `IngredientMapping` tier is dropped in
    Phase C; until then it sits *below* aliases as the temporary fallback). On duplicate
    aliases across products, last-writer-wins — log/note it.
  - Fold staples into stock:
    `in_stock_ids |= {p.id for p in GrocyProduct.select() if p.always_available}`.
    The existing group tier (`any(p in in_stock_ids ...)`) then picks up flagged members for
    free. Note: `always_available` affects **cocktail ingredient availability only** — it does
    not make a product appear as a listed beverage (beverages still key off real stock > 0).
- **Companion:** ensure the strict-availability fix
  `available = all_matched_in_stock and not unmatched` is in place — `always_available` is the
  mitigation that keeps it from over-hiding.

### Phase B — One-time seed script

- `app/scripts/migrate_mappings_to_grocy.py` (standalone). Reads `IngredientMapping`
  (`notion_ingredient_name`, `grocy_product_id`), groups names by product, and **merges** them
  into each product's existing `notion_aliases` via `PUT /api/userfields/products/{id}` (read
  current value first so we don't clobber manual entries). Idempotent; reuses `GrocyClient`
  credentials/SSL handling. Run locally against the dev DB, then in prod against the volume DB.
- **Verify** in the Grocy UI that aliases landed on the expected products before Phase C.

### Phase C — Retire `IngredientMapping`

- Remove the matcher's `IngredientMapping` fallback tier (crafted_drinks.py:69-73, 106).
- Delete `app/routers/mappings.py` and unregister it; remove `MappingEntry`,
  `MappingsResponse`, `CreateMappingRequest` from `app/models.py`; remove the `IngredientMapping`
  model from `app/db.py` and drop it from `init_db`'s `create_tables` list.
- **Frontend:** remove the `/api/mappings` fetch and `mappings` state in `app/static/app.js`
  `init` (lines ~94-101) and the `mappings: []` field.
- **Diagnostics:** the host already sees *why* a drink is hidden — host mode shows all drinks
  with per-ingredient `unmatched`/`out of stock` flags and the `unmatched_ingredients` list in
  the prep panel. That replaces the old `/api/mappings` "unmatched" list (which was anyway
  divergent — it counted only names lacking an explicit row, ignoring name/group matches). No
  replacement endpoint needed.

---

## Tests

- **`tests/test_grocy_client.py`** — `parse_product` with inline userfields, with the field
  absent (degrades cleanly), alias splitting, and `always_available` bool coercion.
- **`tests/test_crafted_drinks_controller.py`** — alias-tier match; `always_available` product
  counts as in stock; a flagged staple keeps an otherwise-makeable drink `available=True`;
  remove/replace the `IngredientMapping`-based matching tests.
- **`tests/test_db.py`** — `GrocyProduct.upsert_all` round-trips `aliases`/`always_available`.
- Remove the `/api/mappings` router tests if any.

## Verification

- **Tests:** `.venv/bin/python -m pytest tests/ -v`.
- **Local:** define the two userfields in Grocy; tag a couple of products (e.g. alias
  `Ginger Beer` → your ginger beer product; `always_available` on a garnish). Run the seed
  script. `cd app && uvicorn main:app --reload --port 8000`:
  - A drink whose only gap was an unmatched staple now appears for guests once flagged/aliased.
  - Host mode (`?host=true`) shows the alias resolving (no "unmatched" on that ingredient).
  - `/api/mappings` is gone (404); the page still loads (no console error from the removed
    fetch).
- **Prod rollout (ordered):** deploy Phase A+B → run seed script against the volume DB → verify
  aliases in Grocy → deploy Phase C → **delete `beverage.db`** (now pure cache) so it rebuilds
  with the new schema → `?host=true` → Refresh to warm caches.

---

## Out of scope — follow-up

- **Retire SQLite for an in-memory cache.** Once mappings live in Grocy, `beverage.db` holds no
  precious data, so persistence could be replaced with in-process caching (module-level state
  reusing the existing `CacheStatus` staleness timestamps, or `cachetools.TTLCache`). That would
  drop peewee, the FK-hardening in `beverages._drop_dangling_refs`, the upsert/replace_all
  machinery, and the DB volume. Deferred to its own plan because it touches every controller and
  carries a multi-worker caveat (each uvicorn worker would cache independently — fine at the
  current single-worker container, but a constraint to confirm). The "delete `beverage.db`" step
  above is a preview of this direction.
