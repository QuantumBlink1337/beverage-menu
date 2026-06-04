import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../app"))

from unittest.mock import AsyncMock, patch

import pytest
from peewee import SqliteDatabase

from controllers.crafted_drinks import _build_response, get_crafted_drinks, refresh
from db import (
    CacheStatus,
    CraftedDrink as DBCraftedDrink,
    CraftedDrinkIngredient,
    GrocyProduct,
    GrocyProductGroup,
    GrocyStockEntry,
    IngredientMapping,
    init_db,
)


@pytest.fixture(autouse=True)
def memory_db():
    db = SqliteDatabase(":memory:", pragmas={"foreign_keys": 1})
    init_db(db)
    yield db
    db.close()


def _seed_drink(notion_page_id="page-1", name="Amaretto Sour", glassware="Rocks",
                tags=None, equipment=None, method=None, notes=None, author=None):
    return DBCraftedDrink.create(
        notion_page_id=notion_page_id,
        name=name,
        glassware=glassware,
        tags=tags or ["NYE"],
        equipment=equipment or [],
        method=method,
        notes=notes,
        author=author,
    )


def _seed_ingredient(drink, ingredient="Amaretto", amount=1.5, unit="oz"):
    return CraftedDrinkIngredient.create(
        drink=drink,
        ingredient=ingredient,
        amount=amount,
        unit=unit,
    )


def _seed_grocy_product(id=1):
    GrocyProductGroup.create(id=1, name="Alcohol")
    GrocyProduct.create(id=id, name="Amaretto", product_group_id=1)


def _seed_stock(product_id=1, amount=1.0):
    GrocyStockEntry.create(
        product_id=product_id,
        amount=amount,
        location_name=None,
        stock_unit_name=None,
    )


def _seed_mapping(ingredient="Amaretto", product_id=1):
    IngredientMapping.create(notion_ingredient_name=ingredient, grocy_product_id=product_id)


# ---------------------------------------------------------------------------
# TestBuildResponseAvailability
# ---------------------------------------------------------------------------

class TestBuildResponseAvailability:
    def test_available_when_all_matched_ingredients_in_stock(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Amaretto")
        _seed_grocy_product()
        _seed_stock(amount=1.0)
        _seed_mapping()

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].available is True

    def test_unavailable_when_matched_ingredient_out_of_stock(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Amaretto")
        _seed_grocy_product()
        _seed_stock(amount=0.0)
        _seed_mapping()

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].available is False

    def test_available_when_all_ingredients_unmatched(self):
        # Can't determine unavailability without mappings — treat as available.
        drink = _seed_drink()
        _seed_ingredient(drink, "Mystery Spirit")

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].available is True

    def test_unmatched_ingredient_does_not_affect_availability(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Amaretto")
        _seed_ingredient(drink, "Mystery Spirit")
        _seed_grocy_product()
        _seed_stock(amount=1.0)
        _seed_mapping()

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].available is True

    def test_unavailable_when_one_of_two_matched_out_of_stock(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Amaretto")
        _seed_ingredient(drink, "Bourbon")
        GrocyProductGroup.create(id=1, name="Alcohol")
        GrocyProduct.create(id=1, name="Amaretto", product_group_id=1)
        GrocyProduct.create(id=2, name="Bourbon", product_group_id=1)
        _seed_stock(product_id=1, amount=1.0)
        _seed_stock(product_id=2, amount=0.0)
        IngredientMapping.create(notion_ingredient_name="Amaretto", grocy_product_id=1)
        IngredientMapping.create(notion_ingredient_name="Bourbon", grocy_product_id=2)

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].available is False


# ---------------------------------------------------------------------------
# TestBuildResponseIngredients
# ---------------------------------------------------------------------------

class TestBuildResponseIngredients:
    def test_matched_ingredient_detail(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Amaretto", amount=1.5, unit="oz")
        _seed_grocy_product()
        _seed_stock(amount=2.0)
        _seed_mapping()

        result = _build_response(host_mode=False)
        ing = result.crafted_drinks[0].ingredients[0]
        assert ing.ingredient == "Amaretto"
        assert ing.amount == 1.5
        assert ing.unit == "oz"
        assert ing.matched is True
        assert ing.in_stock is True

    def test_unmatched_ingredient_detail(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Mystery Spirit")

        result = _build_response(host_mode=False)
        ing = result.crafted_drinks[0].ingredients[0]
        assert ing.matched is False
        assert ing.in_stock is False


# ---------------------------------------------------------------------------
# TestBuildResponseHostMode
# ---------------------------------------------------------------------------

class TestBuildResponseHostMode:
    def test_host_notes_hidden_in_guest_mode(self):
        _seed_drink(notes="Use cask-proof bourbon")

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].host_notes is None

    def test_host_notes_shown_in_host_mode(self):
        _seed_drink(notes="Use cask-proof bourbon")

        result = _build_response(host_mode=True)
        assert result.crafted_drinks[0].host_notes == "Use cask-proof bourbon"

    def test_author_hidden_in_guest_mode(self):
        _seed_drink(author="Matt")

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].author is None

    def test_author_shown_in_host_mode(self):
        _seed_drink(author="Matt")

        result = _build_response(host_mode=True)
        assert result.crafted_drinks[0].author == "Matt"

    def test_unmatched_ingredients_hidden_in_guest_mode(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Mystery Spirit")

        result = _build_response(host_mode=False)
        assert result.crafted_drinks[0].unmatched_ingredients == []

    def test_unmatched_ingredients_shown_in_host_mode(self):
        drink = _seed_drink()
        _seed_ingredient(drink, "Mystery Spirit")

        result = _build_response(host_mode=True)
        assert result.crafted_drinks[0].unmatched_ingredients == ["Mystery Spirit"]


# ---------------------------------------------------------------------------
# TestBuildResponseTagFilter
# ---------------------------------------------------------------------------

class TestBuildResponseTagFilter:
    def test_returns_all_drinks_when_no_tag_filter(self):
        _seed_drink(notion_page_id="page-1", tags=["NYE"])
        _seed_drink(notion_page_id="page-2", name="Negroni", tags=["Summer"])

        result = _build_response(host_mode=False)
        assert len(result.crafted_drinks) == 2

    def test_filters_by_matching_tag(self):
        _seed_drink(notion_page_id="page-1", tags=["NYE"])
        _seed_drink(notion_page_id="page-2", name="Negroni", tags=["Summer"])

        result = _build_response(host_mode=False, tags=["NYE"])
        assert len(result.crafted_drinks) == 1
        assert result.crafted_drinks[0].name == "Amaretto Sour"

    def test_includes_drink_matching_any_tag(self):
        _seed_drink(notion_page_id="page-1", tags=["NYE", "Citrus"])

        result = _build_response(host_mode=False, tags=["Citrus", "Summer"])
        assert len(result.crafted_drinks) == 1

    def test_excludes_drink_matching_no_tags(self):
        _seed_drink(tags=["Winter"])

        result = _build_response(host_mode=False, tags=["NYE"])
        assert result.crafted_drinks == []

    def test_empty_db_returns_empty(self):
        result = _build_response(host_mode=False)
        assert result.crafted_drinks == []


# ---------------------------------------------------------------------------
# TestGetCraftedDrinks (cache-check flow)
# ---------------------------------------------------------------------------

class TestGetCraftedDrinks:
    @pytest.mark.asyncio
    async def test_triggers_refresh_when_cache_stale(self):
        with patch("controllers.crafted_drinks.refresh", new=AsyncMock()) as mock_refresh:
            await get_crafted_drinks()
        mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_refresh_when_cache_fresh(self):
        CacheStatus.mark_recipe_refreshed()
        with patch("controllers.crafted_drinks.refresh", new=AsyncMock()) as mock_refresh:
            await get_crafted_drinks()
        mock_refresh.assert_not_called()
