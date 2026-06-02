# Notion API — Observed Response Shapes

Verified against the live Crafted Drinks database via REPL on 2026-06-02.
Database ID: `3729babcc3ed806caf86cdaf17fd8e91`

---

## Crafted Drinks database

### `GET /databases/{database_id}/query`

Each result is a **page object**. Relevant fields:

```
page["id"]                                                        → str (Notion page UUID)
page["properties"]["Name"]["title"][0]["plain_text"]              → str
page["properties"]["Glassware"]["select"]                         → dict | None
page["properties"]["Glassware"]["select"]["name"]                 → str (if select not None)
page["properties"]["Tags"]["multi_select"]                        → list[dict]
page["properties"]["Tags"]["multi_select"][n]["name"]             → str
page["properties"]["Notes"]["rich_text"]                          → list[dict]
page["properties"]["Notes"]["rich_text"][n]["plain_text"]         → str
page["properties"]["Author"]["rich_text"]                         → list[dict]
page["properties"]["Author"]["rich_text"][n]["plain_text"]        → str
```

**Extraction patterns:**
```python
id        = page["id"]
name      = page["properties"]["Name"]["title"][0]["plain_text"]
glassware = (page["properties"]["Glassware"]["select"] or {}).get("name")
tags      = [t["name"] for t in page["properties"]["Tags"]["multi_select"]]
notes     = "".join(r["plain_text"] for r in page["properties"]["Notes"]["rich_text"]) or None
author    = "".join(r["plain_text"] for r in page["properties"]["Author"]["rich_text"]) or None
```

**Glassware select options (as of 2026-06-02):** Rocks, Coupe, Wine, Flute, Highball

**Tags multi-select options (as of 2026-06-02):** NYE, Alcohol

---

## Per-page blocks

### `GET /blocks/{page_id}/children`

Returns a flat ordered list of block objects. Block types observed on crafted drink pages:

| `type` | Content | Usage |
|---|---|---|
| `child_database` | `block["child_database"]["title"]`, `block["id"]` | Locate Ingredients and Equipment DBs |
| `heading_3` | Label only ("Instructions") | Skip |
| `numbered_list_item` | `block["numbered_list_item"]["rich_text"][n]["plain_text"]` | Collect in order → `method` |
| `paragraph` (empty) | — | Skip |

**Extraction pattern:**
```python
db_ids = {}
steps = []

for block in blocks:
    if block["type"] == "child_database":
        title = block["child_database"]["title"]   # "Ingredients" or "Equipment"
        db_ids[title] = block["id"]
    elif block["type"] == "numbered_list_item":
        step = block["numbered_list_item"]["rich_text"][0]["plain_text"]
        steps.append(step)

ingredients_db_id = db_ids.get("Ingredients")
equipment_db_id   = db_ids.get("Equipment")
method            = "\n".join(steps) or None
```

---

## Ingredients database

### `GET /databases/{ingredients_db_id}/query`

Each result is a page object. The database is embedded per crafted drink page.

```
row["properties"]["Ingredient"]["title"][0]["plain_text"]   → str
row["properties"]["Amount"]["number"]                       → float | None
row["properties"]["Unit"]["select"]                         → dict | None
row["properties"]["Unit"]["select"]["name"]                 → str (if select not None)
```

**Extraction pattern:**
```python
ingredient = row["properties"]["Ingredient"]["title"][0]["plain_text"]
amount     = row["properties"]["Amount"]["number"]
unit       = (row["properties"]["Unit"]["select"] or {}).get("name")
```

**Unit select options (as of 2026-06-02):** oz, piece

---

## Equipment database

### `GET /databases/{equipment_db_id}/query`

Each result is a page object. The database is embedded per crafted drink page.

```
row["properties"]["Name"]["title"][0]["plain_text"]   → str
```

**Extraction pattern:**
```python
name = row["properties"]["Name"]["title"][0]["plain_text"]
```

---

## Notes

- `rich_text` fields are always arrays. Use `"".join(r["plain_text"] for r in ...)` to flatten.
- `select` fields can be `None` if no option is selected — always guard before accessing `.name`.
- Each row in an embedded database is a full Notion page object (same shape as top-level pages).
- `child_database` block `id` doubles as the database ID for querying that embedded database.
- The template page (`Cocktail Template`) lives in the database and will be returned by queries — filter it out by name or mark it `in_trash` when ready.
