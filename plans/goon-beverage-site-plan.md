# GOON Beverage Site — Project Plan

## Overview

A self-hosted beverage display and cocktail recipe site for home hosting. Guests can browse available drinks and cocktails. The host gets a richer view with stock levels, prep notes, and tools for managing the site. Cocktail menus can be filtered by tag and exported to PDF for printing.

---

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Beverage inventory | Grocy (Unraid) | REST API, community app install |
| Backend | Python FastAPI | Proxies Grocy + Notion, serves static files |
| Cocktail recipes | Notion API | Read-only from app |
| Ingredient mapping | SQLite | Links Notion ingredient names to Grocy product IDs |
| Frontend | HTML + Alpine.js | No build step, served by FastAPI |
| Hosting | Tailscale Serve | HTTPS termination, no Nginx needed |
| Remote access | Tailscale Funnel | Optional, no Tailnet required for guests |
| Domain | Custom subdomain | CNAME → MagicDNS hostname |

---

## Hosting & Infrastructure

### Unraid setup
- Grocy installed via Community Applications
- FastAPI runs as a single Docker container
- Tailscale installed via Unraid plugin
- Tailscale Serve configured at host level, forwarding to FastAPI container port

### Networking
- Local access: `http://unraid-ip:port` (guests on home network)
- Remote access (you): Tailscale Serve over HTTPS
- Domain: `drinks.yourdomain.com` CNAME'd to `unraid.tail1234.ts.net`
- Tailscale Funnel available if public guest access ever needed

### Container structure
```
app/
├── main.py
├── routers/
│   ├── beverages.py
│   └── cocktails.py
├── grocy_client.py
├── notion_client.py
├── db.py                  # SQLite DAOs
├── static/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── Dockerfile
└── .env
```

FastAPI mounts `static/` via `StaticFiles` and serves it at `/`. API routes live at `/api/*`.

### Local development
- Run FastAPI bare: `uvicorn main:app --reload --port 8000`
- Static files served directly by FastAPI, no separate server needed
- Grocy on Unraid used directly (no local container)
- `.env` points at Unraid IP for `GROCY_URL`
- Frontend switches API base URL based on hostname:

```js
const API_BASE = window.location.hostname === 'localhost'
  ? 'http://localhost:8000'
  : '/api';
```

---

## Grocy Data Model

### Product groups (flat, one level)
- Beer
- Wine
- Liquor
- Coffee
- Tea

Display grouping (Alcohol = Beer + Wine + Liquor) is reconstructed in the app layer, not in Grocy.

### Naming convention
- Products with variants: `Brand | Variant` (e.g. `High Noon | Pineapple`, `Nespresso | Voltesso`)
- Standalone products: plain name (e.g. `English Breakfast`, `Buffalo Trace`)

### Parent/child products
- Used only when a brand has meaningful trackable variants
- Parent: `no_own_stock = 1`, no direct stock
- Children: `parent_product_id` set to parent, stock tracked individually
- Examples: High Noon flavors, Nespresso pods

### Stock units
| Category | Stock unit | Purchase unit | Notes |
|---|---|---|---|
| Beer/seltzer | Can | Pack (12, 8, etc.) | Conversion defined per product |
| Wine | Bottle | Bottle | 1:1 |
| Liquor | Bottle | Bottle | 1:1, no volume tracking |
| Coffee (pods) | Pod | Box | Conversion defined per product |
| Coffee (other) | g or unit | Bag/unit | As appropriate |
| Tea | Teabag or g | Box | As appropriate |

### Description field
Used for host-facing serving/preparation notes only. Never shown to guests.

Examples:
- Tea: `loose leaf, steep 4 mins at 90°C`
- Beer: `serve with lemon`
- Wine: `decant 30 mins before serving`
- Coffee: `medium grind, filter only`

### Due dates
- Most products: set to "Never overdue"
- Wine: revisit — may want to track opened bottles via `default_best_before_days_after_open`

### Variety packs
No special modeling. When stocking a variety pack, add quantity manually per flavor child product. The pack is a purchasing detail only.

---

## Notion Schema

### Crafted Drinks database (one row per drink)

| Property | Type | Notes |
|---|---|---|
| Name | Title | Drink name |
| Glassware | Select | Rocks, Coupe, Wine, Flute, Highball |
| Tags | Multi-select | NYE, Alcohol, etc. |
| Equipment | Multi-select | Cocktail Shaker, Strainer, Jigger, etc. |
| Notes | Text | Prep tips, sourcing notes — host mode only |
| Author | Text | Host mode only |

Page content (freeform):
- Method/steps as a numbered list

### Per drink page — embedded ingredients database

| Column | Type | Notes |
|---|---|---|
| Ingredient | Title | e.g. "Vodka", "Amaretto", "Lemon juice" |
| Amount | Number | e.g. 1.5 |
| Unit | Select | oz, piece (grows over time) |

### API call cost
- 1 call to fetch all drink pages and their properties (includes Equipment, Tags, etc.)
- 1 call per drink to fetch page blocks (to locate the Ingredients DB ID and extract method steps)
- 1 call per drink to query the embedded Ingredients database
- Total for 40 drinks: ~81 calls, ~27s refresh at 3 req/s

### Workflow
- A master template page exists in the database with the Ingredients database pre-built
- To add a drink: clone the template, rename it, fill in properties, populate the ingredients database
- App never writes to Notion — strictly read-only

---

## SQLite Schema

### `ingredient_mapping` table
```sql
CREATE TABLE ingredient_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notion_ingredient_name TEXT NOT NULL UNIQUE,
    grocy_product_id INTEGER NOT NULL
);
```

### `notion_cache` table
```sql
CREATE TABLE notion_cache (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL,   -- JSON-serialised payload
    cached_at TEXT NOT NULL  -- ISO-8601 UTC timestamp
);
```

Rows are keyed by a stable string (e.g. `"crafted_drinks"`). The entire crafted drinks payload — properties, blocks, ingredients, equipment — is serialised to JSON and stored as a single row.

### Cache TTL and refresh

- **TTL: 12 hours.** On each request the router checks `cached_at`; if the cache is older than 12 hours it triggers a background refresh.
- **Startup refresh.** On app startup, if no cache row exists the cache is populated before the first request is served.
- **Manual refresh endpoint.** `POST /api/crafted_drinks/refresh` (host mode only) triggers an immediate background refresh regardless of TTL. Used by the host-facing "Refresh" button on the website.
- **Background execution.** All refreshes run as FastAPI `BackgroundTask`s — the triggering request returns immediately and the refresh happens asynchronously.

### Notion API throttle

The Notion client enforces a maximum of 3 requests/second during cache refresh using an `asyncio.Semaphore`. With 40 crafted drinks, a full refresh costs ~121 API calls and takes ~40 seconds. This is acceptable as a background operation.

### Matching logic
- Exact name match only, no fuzzy matching
- If `notion_ingredient_name` has no row, ingredient is considered unmatched
- Unmatched ingredients surface in host mode as a warning
- Host mode UI allows assigning a Grocy product to any unmatched ingredient — no raw SQL needed

### Usage
FastAPI reads crafted drinks from the `notion_cache` SQLite table. The Notion API is only contacted during cache refresh. Ingredient names from the cached payload are looked up against `ingredient_mapping` to get Grocy product IDs, which are then checked against live Grocy stock.

---

## FastAPI — Endpoints

### Beverages

**`GET /api/beverages`**

Returns all in-stock products grouped for display.

Fetch flow:
1. `GET /api/objects/products` — all product definitions
2. `GET /api/stock` — all current stock entries
3. Join on `product_id`, filter to `amount > 0`
4. Group children under parents using `parent_product_id`
5. Resolve `product_group_id` to group name
6. Parse `Brand | Variant` names into `brand` and `variant` fields
7. Include `description` field (host mode only — stripped in guest responses)
8. Return structured response

Response shape:
```json
{
  "groups": [
    {
      "name": "Beer",
      "display_group": "Alcohol",
      "products": [
        {
          "id": 2,
          "name": "High Noon",
          "variants": [
            {
              "id": 1,
              "name": "Pineapple",
              "amount": 3,
              "unit": "Can",
              "location": "Fridge",
              "serving_notes": null
            }
          ]
        }
      ]
    }
  ]
}
```

---

### Crafted Drinks

**`GET /api/crafted_drinks`**

Returns all crafted drinks with availability computed.

Fetch flow:
1. Read crafted drinks payload from `notion_cache` SQLite table
2. If cache is missing or older than 12 hours, trigger background refresh and serve stale data (or empty if no cache exists yet)
3. For each ingredient name, look up `grocy_product_id` in SQLite `ingredient_mapping`
4. For each matched product ID, check Grocy stock (`amount > 0`)
5. Compute `available: true` only if all matched ingredients are in stock
6. Unmatched ingredients do not fail availability — they are flagged separately in host response
7. Strip `notes` and `author` from guest responses
8. Return structured response

**`GET /api/crafted_drinks?tags=NYE,Summer`**

Same flow, filtered to crafted drinks whose tags intersect the provided list. Used for PDF export.

**`POST /api/crafted_drinks/refresh`** *(host mode only)*

Triggers an immediate background refresh of the Notion cache. Returns `202 Accepted` immediately; refresh runs asynchronously. Used by the host-facing "Refresh" button.

Response shape:
```json
{
  "cocktails": [
    {
      "id": "notion-page-id",
      "name": "Amaretto Sour",
      "glassware": "Rocks",
      "tags": ["NYE", "Citrus"],
      "garnish": "Lemon twist, 2 brandied cherries",
      "method": "Dry shake, then shake with ice, strain over fresh ice.",
      "host_notes": "Use cask-proof bourbon for best results.",
      "available": true,
      "ingredients": [
        {
          "ingredient": "Amaretto",
          "amount": 1.5,
          "unit": "oz",
          "in_stock": true,
          "matched": true
        },
        {
          "ingredient": "Bourbon",
          "amount": 0.75,
          "unit": "oz",
          "in_stock": true,
          "matched": true
        }
      ],
      "unmatched_ingredients": []
    }
  ]
}
```

**`GET /api/cocktails?tags=NYE,Summer`**

Same flow, filtered to cocktails whose tags intersect the provided list. Used for PDF export.

---

### Ingredient mapping (host mode only)

**`GET /api/mappings`**

Returns all current mappings plus a list of unmatched ingredient names (ingredient names found in Notion that have no SQLite row).

**`POST /api/mappings`**

Body: `{ "notion_ingredient_name": "Bourbon", "grocy_product_id": 5 }`

Creates a new mapping.

**`DELETE /api/mappings/{id}`**

Removes a mapping.

---

## Guest vs Host Mode

Toggled via `?host=true` query parameter. No authentication. Client-side only — FastAPI does not enforce mode, but host-only fields (`host_notes`, `serving_notes`, unmatched ingredient warnings, mapping UI) are only rendered when `host=true` is present.

### Guest view
- Only shows products with `amount > 0`
- Only shows cocktails where `available: true`
- No serving notes or prep details
- No stock quantities
- Clean, minimal presentation

### Host view (all of the above plus)
- All cocktails shown regardless of availability
- Unavailability indicator on cocktails with missing ingredients
- Unmatched ingredient warnings
- Ingredient mapping management UI
- Stock quantities shown
- Serving notes from Grocy description field
- Host notes from Notion

---

## PDF / Print Export

Implemented via `@media print` stylesheet — no dependencies.

### Flow
1. Host selects one or more tags from a filter UI
2. Frontend filters cocktail list to matching cocktails
3. Host clicks "Print / Export PDF"
4. Print stylesheet takes over:
   - Hides navigation, controls, host-only UI elements
   - Renders only the filtered cocktail cards
   - Each cocktail card gets a clean layout: name, glassware, ingredients table, method, garnish
   - Page breaks inserted between cocktails
5. Browser print dialog handles PDF generation

### Print stylesheet considerations
- Hide: nav, tag filter UI, availability indicators, host notes, mapping UI
- Show: cocktail name, glassware, ingredients (ingredient + amount + unit), method, garnish
- Page break: `page-break-after: always` or `break-after: page` per card
- Font size bumped slightly for readability on paper

---

## Frontend Structure

Single page app using Alpine.js. No build step.

### State
```js
{
  mode: 'guest' | 'host',     // derived from ?host=true
  activeSection: 'beverages' | 'cocktails',
  selectedTags: [],            // for cocktail filtering + PDF export
  beverages: [],               // loaded from /api/beverages
  cocktails: [],               // loaded from /api/cocktails
  mappings: []                 // host mode only, from /api/mappings
}
```

### Sections
- **Beverages** — grouped by display group (Alcohol, Coffee, Tea), cards per product/variant
- **Cocktails** — filterable by tag, cards showing name/glassware/availability, expandable to full recipe
- **Mappings** (host only) — list of unmatched ingredients with Grocy product assignment UI

### Tag filter
Multi-select tag pills above the cocktail list. Selecting tags filters the list live. Selected tags also drive the PDF export scope.

---

## Open Questions / Future Considerations

- Wine due date tracking (opened bottle expiry)
- Caching layer for Notion API responses (Notion API can be slow)
- Cocktail images (Notion supports cover images on pages — could be surfaced)
- "Mark as made" feature that decrements Grocy stock per cocktail serving (would require write access to Grocy)
