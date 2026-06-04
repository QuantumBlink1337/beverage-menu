import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../app"))

import pytest
from peewee import IntegrityError, SqliteDatabase

from db import (
    CacheStatus,
    CraftedDrink,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group(id=1, name="Beer"):
    return {"id": id, "name": name}


def _product(id=1, name="High Noon", product_group_id=1, parent_product_id=None,
             no_own_stock=False, description=None):
    return {
        "id": id,
        "name": name,
        "product_group_id": product_group_id,
        "parent_product_id": parent_product_id,
        "no_own_stock": no_own_stock,
        "description": description,
    }


def _stock(product_id=1, amount=3.0, location_name="Fridge", stock_unit_name="Can"):
    return {"product_id": product_id, "amount": amount,
            "location_name": location_name, "stock_unit_name": stock_unit_name}


_DRINK = {
    "notion_page_id": "page-1",
    "name": "Amaretto Sour",
    "glassware": "Rocks",
    "tags": ["NYE", "Alcohol"],
    "equipment": ["Cocktail Shaker", "Strainer"],
    "method": "Dry shake.\nShake with ice.",
    "notes": "Use cask-proof bourbon.",
    "author": "Matt",
    "ingredients": [
        {"ingredient": "Amaretto", "amount": 1.5, "unit": "oz"},
        {"ingredient": "Lemon juice", "amount": 0.75, "unit": "oz"},
    ],
}


def _drink(**overrides):
    d = _DRINK.copy()
    d["ingredients"] = [i.copy() for i in _DRINK["ingredients"]]
    d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# CacheStatus
# ---------------------------------------------------------------------------

class TestCacheStatus:
    def test_is_recipe_stale_when_empty(self):
        assert CacheStatus.is_recipe_stale() is True

    def test_is_grocy_stale_when_empty(self):
        assert CacheStatus.is_grocy_stale() is True

    def test_mark_recipe_refreshed_clears_staleness(self):
        CacheStatus.mark_recipe_refreshed()
        assert CacheStatus.is_recipe_stale() is False

    def test_mark_grocy_refreshed_clears_staleness(self):
        CacheStatus.mark_grocy_refreshed()
        assert CacheStatus.is_grocy_stale() is False

    def test_recipe_stale_after_ttl(self):
        CacheStatus.mark_recipe_refreshed()
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        CacheStatus.update(last_refreshed_at=old).where(
            CacheStatus.cache_key == "crafted_drinks"
        ).execute()
        assert CacheStatus.is_recipe_stale(ttl_hours=24) is True

    def test_grocy_stale_after_ttl(self):
        CacheStatus.mark_grocy_refreshed()
        old = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        CacheStatus.update(last_refreshed_at=old).where(
            CacheStatus.cache_key == "grocy"
        ).execute()
        assert CacheStatus.is_grocy_stale(ttl_minutes=10) is True

    def test_mark_refreshed_is_idempotent(self):
        CacheStatus.mark_recipe_refreshed()
        CacheStatus.mark_recipe_refreshed()
        assert CacheStatus.select().count() == 1

    def test_recipe_and_grocy_are_independent(self):
        CacheStatus.mark_recipe_refreshed()
        assert CacheStatus.is_grocy_stale() is True


# ---------------------------------------------------------------------------
# CraftedDrink
# ---------------------------------------------------------------------------

class TestCraftedDrink:
    def test_replace_all_creates_drinks(self):
        CraftedDrink.replace_all([_drink()])
        assert CraftedDrink.select().count() == 1

    def test_replace_all_stores_ingredients(self):
        CraftedDrink.replace_all([_drink()])
        assert CraftedDrinkIngredient.select().count() == 2

    def test_replace_all_clears_previous(self):
        CraftedDrink.replace_all([_drink()])
        CraftedDrink.replace_all([_drink(notion_page_id="page-2", name="Negroni", ingredients=[])])
        assert CraftedDrink.select().count() == 1
        assert CraftedDrinkIngredient.select().count() == 0

    def test_json_list_fields_roundtrip(self):
        CraftedDrink.replace_all([_drink()])
        drink = CraftedDrink.get_by_id("page-1")
        assert drink.tags == ["NYE", "Alcohol"]
        assert drink.equipment == ["Cocktail Shaker", "Strainer"]

    def test_empty_list_fields(self):
        CraftedDrink.replace_all([_drink(tags=[], equipment=[])])
        drink = CraftedDrink.get_by_id("page-1")
        assert drink.tags == []
        assert drink.equipment == []

    def test_ingredients_backref(self):
        CraftedDrink.replace_all([_drink()])
        drink = CraftedDrink.get_by_id("page-1")
        names = {i.ingredient for i in drink.ingredients}
        assert names == {"Amaretto", "Lemon juice"}


# ---------------------------------------------------------------------------
# Grocy models
# ---------------------------------------------------------------------------

class TestGrocyModels:
    def test_upsert_product_groups(self):
        GrocyProductGroup.upsert_all([_group(id=1, name="Beer"), _group(id=2, name="Wine")])
        assert GrocyProductGroup.select().count() == 2

    def test_upsert_product_groups_updates_name(self):
        GrocyProductGroup.upsert_all([_group(id=1, name="Beer")])
        GrocyProductGroup.upsert_all([_group(id=1, name="Craft Beer")])
        assert GrocyProductGroup.select().count() == 1
        assert GrocyProductGroup.get_by_id(1).name == "Craft Beer"

    def test_upsert_products(self):
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([_product()])
        assert GrocyProduct.select().count() == 1

    def test_upsert_products_updates_existing(self):
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([_product(name="High Noon")])
        GrocyProduct.upsert_all([_product(name="High Noon Updated")])
        assert GrocyProduct.select().count() == 1
        assert GrocyProduct.get_by_id(1).name == "High Noon Updated"

    def test_upsert_preserves_ingredient_mapping_fk(self):
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([_product()])
        product = GrocyProduct.get_by_id(1)
        IngredientMapping.create(notion_ingredient_name="Vodka", grocy_product=product)
        GrocyProduct.upsert_all([_product(name="High Noon Renamed")])
        mapping = IngredientMapping.get(IngredientMapping.notion_ingredient_name == "Vodka")
        assert mapping.grocy_product_id == 1

    def test_product_parent_child(self):
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([
            _product(id=1, name="High Noon", no_own_stock=True),
            _product(id=2, name="High Noon | Pineapple", parent_product_id=1),
        ])
        child = GrocyProduct.get_by_id(2)
        assert child.parent_product_id == 1

    def test_upsert_child_before_parent_in_list(self):
        # API response may return children before their parent — upsert_all must
        # sort to insert parents first or the self-referential FK will fail.
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([
            _product(id=2, name="High Noon | Pineapple", parent_product_id=1),
            _product(id=1, name="High Noon", no_own_stock=True),
        ])
        assert GrocyProduct.select().count() == 2

    def test_replace_stock_entries(self):
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([_product()])
        GrocyStockEntry.replace_all([_stock()])
        assert GrocyStockEntry.select().count() == 1

    def test_replace_stock_clears_previous(self):
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([_product()])
        GrocyStockEntry.replace_all([_stock(amount=3.0)])
        GrocyStockEntry.replace_all([_stock(amount=5.0)])
        assert GrocyStockEntry.select().count() == 1
        assert GrocyStockEntry.select().first().amount == 5.0


# ---------------------------------------------------------------------------
# IngredientMapping
# ---------------------------------------------------------------------------

class TestIngredientMapping:
    @pytest.fixture(autouse=True)
    def grocy_product(self):
        GrocyProductGroup.upsert_all([_group()])
        GrocyProduct.upsert_all([_product()])
        return GrocyProduct.get_by_id(1)

    def test_create_and_get_all(self, grocy_product):
        IngredientMapping.create(notion_ingredient_name="Bourbon", grocy_product=grocy_product)
        mappings = list(IngredientMapping.select())
        assert len(mappings) == 1
        assert mappings[0].notion_ingredient_name == "Bourbon"
        assert mappings[0].grocy_product_id == 1

    def test_get_by_ingredient_name(self, grocy_product):
        IngredientMapping.create(notion_ingredient_name="Amaretto", grocy_product=grocy_product)
        row = IngredientMapping.get_or_none(IngredientMapping.notion_ingredient_name == "Amaretto")
        assert row is not None
        assert row.grocy_product_id == 1

    def test_get_by_ingredient_name_missing(self):
        row = IngredientMapping.get_or_none(IngredientMapping.notion_ingredient_name == "Ghost")
        assert row is None

    def test_delete(self, grocy_product):
        mapping = IngredientMapping.create(notion_ingredient_name="Vodka", grocy_product=grocy_product)
        assert IngredientMapping.delete_by_id(mapping.id) == 1
        assert IngredientMapping.select().count() == 0

    def test_unique_constraint(self, grocy_product):
        IngredientMapping.create(notion_ingredient_name="Gin", grocy_product=grocy_product)
        with pytest.raises(IntegrityError):
            IngredientMapping.create(notion_ingredient_name="Gin", grocy_product=grocy_product)
