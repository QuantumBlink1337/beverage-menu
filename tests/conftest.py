import pytest


# ---------------------------------------------------------------------------
# Raw Notion response fixtures — shaped from live API responses (2026-06-02)
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_drink_page():
    """A raw Notion page object representing a crafted drink."""
    return {
        "id": "3739babc-c3ed-80d1-9b43-c6f7731eb9be",
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "Amaretto Sour"}]
            },
            "Glassware": {
                "type": "select",
                "select": {"name": "Rocks"}
            },
            "Tags": {
                "type": "multi_select",
                "multi_select": [
                    {"name": "NYE"},
                    {"name": "Alcohol"}
                ]
            },
            "Equipment": {
                "type": "multi_select",
                "multi_select": [
                    {"name": "Cocktail Shaker"},
                    {"name": "Strainer"}
                ]
            },
            "Notes": {
                "type": "rich_text",
                "rich_text": [{"plain_text": "Use cask-proof bourbon for best results."}]
            },
            "Author": {
                "type": "rich_text",
                "rich_text": [{"plain_text": "Matt"}]
            },
        }
    }


@pytest.fixture
def raw_drink_page_no_glassware(raw_drink_page):
    """A drink page where Glassware has not been selected."""
    page = raw_drink_page.copy()
    page["properties"] = raw_drink_page["properties"].copy()
    page["properties"]["Glassware"] = {"type": "select", "select": None}
    return page


@pytest.fixture
def raw_blocks():
    """Raw page blocks for a crafted drink page."""
    return [
        {
            "type": "child_database",
            "id": "3739babc-c3ed-8073-9c22-cba3d3b46e84",
            "child_database": {"title": "Ingredients"}
        },
        {
            "type": "heading_3",
            "id": "3739babc-c3ed-8007-9262-d8209a9cbc64",
            "heading_3": {"rich_text": [{"plain_text": "Instructions"}]}
        },
        {
            "type": "numbered_list_item",
            "id": "3739babc-c3ed-808f-9999-fcfa7a7e8044",
            "numbered_list_item": {"rich_text": [{"plain_text": "Dry shake all ingredients."}]}
        },
        {
            "type": "numbered_list_item",
            "id": "3739babc-c3ed-80af-950d-db1cd82ffbb0",
            "numbered_list_item": {"rich_text": [{"plain_text": "Shake with ice and strain over a large rock."}]}
        },
        {
            "type": "paragraph",
            "id": "3739babc-c3ed-8078-a362-e4f5437db3a5",
            "paragraph": {"rich_text": []}
        },
    ]


@pytest.fixture
def raw_ingredient_row():
    """A raw Notion page object representing a single ingredient row."""
    return {
        "properties": {
            "Ingredient": {
                "type": "title",
                "title": [{"plain_text": "Amaretto"}]
            },
            "Amount": {
                "type": "number",
                "number": 1.5
            },
            "Unit": {
                "type": "select",
                "select": {"name": "oz"}
            }
        }
    }


@pytest.fixture
def raw_ingredient_row_no_unit(raw_ingredient_row):
    """An ingredient row where Unit has not been selected."""
    row = raw_ingredient_row.copy()
    row["properties"] = raw_ingredient_row["properties"].copy()
    row["properties"]["Unit"] = {"type": "select", "select": None}
    return row
