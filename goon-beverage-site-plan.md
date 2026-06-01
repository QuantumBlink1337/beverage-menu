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

### Cocktails database (one row per cocktail)

| Property | Type | Notes |
|---|---|---|
| Name | Title | Cocktail name |
| Glassware | Select | Rocks, coupe, highball, martini, etc. |
| Tags | Multi-select | NYE, Summer, LOTR, Citrus, Boozy, etc. |
| Garnish | Text | e.g. "lemon twist, 2 brandied cherries" |
| Host Notes | Text | Prep tips, sourcing notes — host mode only |

Page content (freeform):
- Method/steps as written text

### Per cocktail page — embedded ingredients database

| Column | Type | Notes |
|---|---|---|
| Ingredient | Title | e.g. "Vodka", "Amaretto", "Lemon juice" |
| Amount | Number | e.g. 1.5 |
| Unit | Select | oz, ml, dash, tsp, splash, barspoon |

### Workflow
- A master cocktail template page exists in the database with the ingredients database pre-built
- To add a cocktail: clone the template, rename it, fill in properties, populate the ingredients database
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

### Matching logic
- Exact name match only, no fuzzy matching
- If `notion_ingredient_name` has no row, ingredient is considered unmatched
- Unmatched ingredients surface in host mode as a warning
- Host mode UI allows assigning a Grocy product to any unmatched ingredient — no raw SQL needed

### Usage
FastAPI looks up each ingredient name from the embedded Notion database against this table to get a Grocy product ID, then checks Grocy stock for that product ID to determine availability.

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

### Cocktails

**`GET /api/cocktails`**

Returns all cocktails with availability computed.

Fetch flow:
1. Query Notion Cocktails database for all rows + properties
2. For each cocktail page, fetch page content to locate embedded ingredients database block
3. Query each embedded ingredients database for its rows (`Ingredient`, `Amount`, `Unit`)
4. For each ingredient name, look up `grocy_product_id` in SQLite `ingredient_mapping`
5. For each matched product ID, check Grocy stock (`amount > 0`)
6. Compute `available: true` only if all matched ingredients are in stock
7. Unmatched ingredients do not fail availability — they are flagged separately in host response
8. Strip `Host Notes` from guest responses
9. Return structured response

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
