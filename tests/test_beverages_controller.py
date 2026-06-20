import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../app"))

from unittest.mock import AsyncMock, patch

import pytest
from peewee import SqliteDatabase

from controllers.beverages import _build_response, _refresh, _variant_name, get_beverages
from db import (
    CacheStatus,
    GrocyProduct,
    GrocyProductGroup,
    GrocyStockEntry,
    init_db,
)


@pytest.fixture(autouse=True)
def memory_db():
    db = SqliteDatabase(":memory:", pragmas={"foreign_keys": 1})
    init_db(db)
    yield db
    db.close()


def _seed_group(id=1, name="Alcohol"):
    GrocyProductGroup.create(id=id, name=name)


def _seed_product(id, name, group_id=1, parent_id=None, no_own_stock=False, description=None):
    GrocyProduct.create(
        id=id,
        name=name,
        product_group_id=group_id,
        parent_product_id=parent_id,
        no_own_stock=no_own_stock,
        description=description,
    )


def _seed_stock(product_id, amount, location_name=None):
    GrocyStockEntry.create(
        product_id=product_id,
        amount=amount,
        location_name=location_name,
        stock_unit_name=None,
    )


# ---------------------------------------------------------------------------
# TestVariantName
# ---------------------------------------------------------------------------

class TestVariantName:
    def test_splits_brand_variant(self):
        assert _variant_name("High Noon | Pineapple") == "Pineapple"

    def test_returns_full_name_when_no_separator(self):
        assert _variant_name("Buffalo Trace") == "Buffalo Trace"

    def test_only_splits_on_first_separator(self):
        assert _variant_name("A | B | C") == "B | C"


# ---------------------------------------------------------------------------
# TestBuildResponseStandalone
# ---------------------------------------------------------------------------

class TestBuildResponseStandalone:
    def test_returns_in_stock_standalone_product(self):
        _seed_group()
        _seed_product(id=1, name="Buffalo Trace")
        _seed_stock(product_id=1, amount=1.0, location_name="Bar Shelf")

        result = _build_response(host_mode=False)

        assert len(result.groups) == 1
        assert len(result.groups[0].products) == 1
        p = result.groups[0].products[0]
        assert p.id == 1
        assert p.name == "Buffalo Trace"
        assert p.amount == 1.0
        assert p.location == "Bar Shelf"

    def test_excludes_out_of_stock_product(self):
        _seed_group()
        _seed_product(id=1, name="Empty Bottle")
        _seed_stock(product_id=1, amount=0.0)

        result = _build_response(host_mode=False)
        assert result.groups == []

    def test_serving_notes_hidden_in_guest_mode(self):
        _seed_group()
        _seed_product(id=1, name="Buffalo Trace", description="Serve neat")
        _seed_stock(product_id=1, amount=1.0)

        result = _build_response(host_mode=False)
        assert result.groups[0].products[0].serving_notes is None

    def test_serving_notes_shown_in_host_mode(self):
        _seed_group()
        _seed_product(id=1, name="Buffalo Trace", description="Serve neat")
        _seed_stock(product_id=1, amount=1.0)

        result = _build_response(host_mode=True)
        assert result.groups[0].products[0].serving_notes == "Serve neat"

    def test_products_sorted_by_name(self):
        _seed_group()
        _seed_product(id=1, name="Whiskey")
        _seed_product(id=2, name="Amaretto")
        _seed_stock(product_id=1, amount=1.0)
        _seed_stock(product_id=2, amount=1.0)

        result = _build_response(host_mode=False)
        names = [p.name for p in result.groups[0].products]
        assert names == ["Amaretto", "Whiskey"]


# ---------------------------------------------------------------------------
# TestBuildResponseParentChild
# ---------------------------------------------------------------------------

class TestBuildResponseParentChild:
    def test_child_nested_under_parent(self):
        _seed_group()
        _seed_product(id=2, name="High Noon", no_own_stock=True)
        _seed_product(id=1, name="High Noon | Pineapple", parent_id=2)
        _seed_stock(product_id=1, amount=3.0, location_name="Fridge")

        result = _build_response(host_mode=False)

        assert len(result.groups[0].products) == 1
        parent = result.groups[0].products[0]
        assert parent.id == 2
        assert parent.name == "High Noon"
        assert parent.amount is None
        assert len(parent.children) == 1
        child = parent.children[0]
        assert child.id == 1
        assert child.name == "Pineapple"
        assert child.amount == 3.0

    def test_out_of_stock_child_excluded(self):
        _seed_group()
        _seed_product(id=2, name="High Noon", no_own_stock=True)
        _seed_product(id=1, name="High Noon | Pineapple", parent_id=2)
        _seed_product(id=3, name="High Noon | Watermelon", parent_id=2)
        _seed_stock(product_id=1, amount=3.0)
        _seed_stock(product_id=3, amount=0.0)

        result = _build_response(host_mode=False)
        parent = result.groups[0].products[0]
        assert len(parent.children) == 1
        assert parent.children[0].name == "Pineapple"

    def test_parent_absent_when_all_children_out_of_stock(self):
        _seed_group()
        _seed_product(id=2, name="High Noon", no_own_stock=True)
        _seed_product(id=1, name="High Noon | Pineapple", parent_id=2)
        _seed_stock(product_id=1, amount=0.0)

        result = _build_response(host_mode=False)
        assert result.groups == []

    def test_children_sorted_by_name(self):
        _seed_group()
        _seed_product(id=2, name="High Noon", no_own_stock=True)
        _seed_product(id=1, name="High Noon | Watermelon", parent_id=2)
        _seed_product(id=3, name="High Noon | Pineapple", parent_id=2)
        _seed_stock(product_id=1, amount=1.0)
        _seed_stock(product_id=3, amount=1.0)

        result = _build_response(host_mode=False)
        child_names = [c.name for c in result.groups[0].products[0].children]
        assert child_names == ["Pineapple", "Watermelon"]


# ---------------------------------------------------------------------------
# TestBuildResponseGroups
# ---------------------------------------------------------------------------

class TestBuildResponseGroups:
    def test_group_name_passed_through(self):
        GrocyProductGroup.create(id=1, name="Beer")
        _seed_product(id=1, name="Lager", group_id=1)
        _seed_stock(product_id=1, amount=1.0)

        result = _build_response(host_mode=False)
        assert result.groups[0].name == "Beer"

    def test_groups_sorted_by_name(self):
        GrocyProductGroup.create(id=1, name="Wine")
        GrocyProductGroup.create(id=2, name="Coffee")
        _seed_product(id=1, name="Merlot", group_id=1)
        _seed_product(id=2, name="Espresso", group_id=2)
        _seed_stock(product_id=1, amount=1.0)
        _seed_stock(product_id=2, amount=1.0)

        result = _build_response(host_mode=False)
        group_names = [g.name for g in result.groups]
        assert group_names == ["Coffee", "Wine"]

    def test_empty_db_returns_empty_groups(self):
        result = _build_response(host_mode=False)
        assert result.groups == []


# ---------------------------------------------------------------------------
# TestGetBeverages (cache-check flow)
# ---------------------------------------------------------------------------

class TestGetBeverages:
    @pytest.mark.asyncio
    async def test_triggers_refresh_when_cache_stale(self):
        with patch("controllers.beverages._refresh", new=AsyncMock()) as mock_refresh:
            await get_beverages()
        mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_refresh_when_cache_fresh(self):
        CacheStatus.mark_grocy_refreshed()
        with patch("controllers.beverages._refresh", new=AsyncMock()) as mock_refresh:
            await get_beverages()
        mock_refresh.assert_not_called()


# ---------------------------------------------------------------------------
# TestRefreshHardening
# ---------------------------------------------------------------------------

class TestRefreshHardening:
    @pytest.mark.asyncio
    async def test_refresh_nulls_dangling_group_reference(self):
        # A product assigned to a group that no longer exists in Grocy must not crash
        # the refresh on the FK constraint (the cold-start bug the smoke test caught).
        from models import (
            GrocyProduct as PGrocyProduct,
            GrocyProductGroup as PGrocyProductGroup,
        )

        client = AsyncMock()
        client.get_product_groups = AsyncMock(
            return_value=[PGrocyProductGroup(id=2, name="Beer")]
        )
        client.get_products = AsyncMock(
            return_value=[PGrocyProduct(id=1, name="High Noon", product_group_id=99)]
        )  # group 99 no longer exists
        client.get_stock = AsyncMock(return_value=[])

        with patch("controllers.beverages.GrocyClient", return_value=client):
            await _refresh()  # must not raise IntegrityError

        stored = GrocyProduct.get(GrocyProduct.id == 1)
        assert stored.product_group_id is None
