# Grocy API — Confirmed Response Shapes (2026-06-03)

All endpoints under `GET /api/objects/{resource}`.
Auth: `GROCY-API-KEY` header.

---

## `GET /api/objects/product_groups`

```json
[
  {
    "id": 1,
    "name": "Alcohol",
    "description": null,
    "row_created_timestamp": "2026-05-31 20:09:20",
    "active": 1
  }
]
```

**Fields used:** `id`, `name`.

---

## `GET /api/objects/products`

```json
[
  {
    "id": 1,
    "name": "High Noon | Pineapple",
    "description": null,
    "product_group_id": 1,
    "parent_product_id": 2,
    "no_own_stock": 0,
    ...
  },
  {
    "id": 2,
    "name": "High Noon ",
    "description": null,
    "product_group_id": 1,
    "parent_product_id": null,
    "no_own_stock": 1,
    ...
  }
]
```

**Fields used:** `id`, `name`, `description`, `product_group_id`, `parent_product_id`, `no_own_stock`.

**Notes:**
- `no_own_stock` is an integer (0 or 1), not a boolean. Pydantic coerces it.
- Product names may have trailing whitespace — strip on parse.
- Many extra fields (`qu_id_*`, `default_best_before_days`, etc.) are ignored.

---

## `GET /api/objects/stock`

```json
[
  {
    "id": 1,
    "product_id": 1,
    "amount": 3,
    "location_id": 2,
    "best_before_date": "2999-12-31",
    "purchased_date": "2026-05-31",
    "stock_id": "6a1cdf25519b5",
    "price": 0,
    "open": 0,
    "opened_date": null,
    "row_created_timestamp": "2026-05-31 20:23:49",
    "note": null
  }
]
```

**Fields used:** `product_id`, `amount`, `location_id`.

**Notes:**
- These are individual stock batch entries, not aggregated totals. A product purchased
  twice has two rows. The client aggregates by `product_id` before persisting.
- `location_id` is a foreign key — resolve to `location_name` via `/api/objects/locations`.
- No unit field. Stock unit lives on the product as `qu_id_stock`, which references
  `/api/objects/quantity_units`. Unit resolution is a follow-up task.

---

## `GET /api/objects/locations`

```json
[
  {
    "id": 2,
    "name": "Fridge",
    "description": null,
    "row_created_timestamp": "2026-05-31 20:05:18",
    "is_freezer": 0,
    "active": 1
  },
  {
    "id": 3,
    "name": "Bar Shelf",
    "description": null,
    "row_created_timestamp": "2026-05-31 20:07:30",
    "is_freezer": 0,
    "active": 1
  },
  {
    "id": 4,
    "name": "Coffee/Tea",
    "description": null,
    "row_created_timestamp": "2026-05-31 20:07:35",
    "is_freezer": 0,
    "active": 1
  }
]
```

**Fields used:** `id`, `name`.

---

## Pending / not yet inspected

- `GET /api/objects/quantity_units` — needed for `stock_unit_name` resolution.
  Each product has `qu_id_stock`; the unit name lives here.
