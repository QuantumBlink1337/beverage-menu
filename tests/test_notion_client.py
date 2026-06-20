import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../app"))

import pytest
from notion_client import NotionClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "secret_test")
    monkeypatch.setenv("NOTION_CRAFTED_DRINKS_DB_ID", "test-db-id")
    return NotionClient()


class TestParseDrinkProperties:
    def test_parses_all_fields(self, client, raw_drink_page):
        result = client.parse_drink_properties(raw_drink_page)
        assert result.page_id == "3739babc-c3ed-80d1-9b43-c6f7731eb9be"
        assert result.name == "Amaretto Sour"
        assert result.glassware == "Rocks"
        assert [(t.name, t.color) for t in result.tags] == [("NYE", "blue"), ("Alcohol", "green")]
        assert result.equipment == ["Cocktail Shaker", "Strainer"]
        assert result.notes == "Use cask-proof bourbon for best results."
        assert result.author == "Matt"

    def test_glassware_none_when_unset(self, client, raw_drink_page_no_glassware):
        result = client.parse_drink_properties(raw_drink_page_no_glassware)
        assert result.glassware is None

    def test_empty_notes_returns_none(self, client, raw_drink_page):
        raw_drink_page["properties"]["Notes"]["rich_text"] = []
        result = client.parse_drink_properties(raw_drink_page)
        assert result.notes is None


class TestParseBlocks:
    def test_extracts_ingredients_db_id(self, client, raw_blocks):
        result = client.parse_blocks(raw_blocks)
        assert result.db_ids["Ingredients"] == "3739babc-c3ed-8073-9c22-cba3d3b46e84"

    def test_extracts_method_steps(self, client, raw_blocks):
        result = client.parse_blocks(raw_blocks)
        assert result.method == "Dry shake all ingredients.\nShake with ice and strain over a large rock."

    def test_skips_non_step_blocks(self, client, raw_blocks):
        result = client.parse_blocks(raw_blocks)
        assert "Instructions" not in result.method
        assert result.method.strip() == result.method

    def test_empty_blocks_returns_empty(self, client):
        result = client.parse_blocks([])
        assert result.db_ids == {}
        assert result.method is None


class TestParseIngredientRow:
    def test_parses_all_fields(self, client, raw_ingredient_row):
        result = client.parse_ingredient_row(raw_ingredient_row)
        assert result.ingredient == "Amaretto"
        assert result.amount == 1.5
        assert result.unit == "oz"

    def test_unit_none_when_unset(self, client, raw_ingredient_row_no_unit):
        result = client.parse_ingredient_row(raw_ingredient_row_no_unit)
        assert result.unit is None
