import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../app"))

from unittest.mock import AsyncMock, patch

import pytest
from grocy_client import GrocyClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GROCY_URL", "http://grocy.local:9283")
    monkeypatch.setenv("GROCY_API_KEY", "test-api-key")
    return GrocyClient()


# ---------------------------------------------------------------------------
# TestParseProductGroup
# ---------------------------------------------------------------------------

class TestParseProductGroup:
    def test_parses_id_and_name(self, client, raw_product_group):
        result = client.parse_product_group(raw_product_group)
        assert result.id == 1
        assert result.name == "Alcohol"

    def test_ignores_extra_fields(self, client, raw_product_group):
        raw_product_group["unexpected_field"] = "ignored"
        result = client.parse_product_group(raw_product_group)
        assert result.id == 1


# ---------------------------------------------------------------------------
# TestParseProduct
# ---------------------------------------------------------------------------

class TestParseProduct:
    def test_parses_child_product(self, client, raw_product_child):
        result = client.parse_product(raw_product_child)
        assert result.id == 1
        assert result.name == "High Noon | Pineapple"
        assert result.product_group_id == 1
        assert result.parent_product_id == 2
        assert result.no_own_stock is False
        assert result.description is None

    def test_parses_parent_product(self, client, raw_product_parent):
        result = client.parse_product(raw_product_parent)
        assert result.id == 2
        assert result.parent_product_id is None
        assert result.no_own_stock is True

    def test_strips_trailing_whitespace_from_name(self, client, raw_product_parent):
        result = client.parse_product(raw_product_parent)
        assert result.name == "High Noon"
        assert not result.name.endswith(" ")

    def test_no_own_stock_integer_coerced_to_bool(self, client, raw_product_child):
        raw_product_child["no_own_stock"] = 1
        result = client.parse_product(raw_product_child)
        assert result.no_own_stock is True

    def test_empty_description_normalised_to_none(self, client, raw_product_child):
        raw_product_child["description"] = ""
        result = client.parse_product(raw_product_child)
        assert result.description is None

    def test_ignores_extra_fields(self, client, raw_product_child):
        raw_product_child["qu_id_stock"] = 6
        result = client.parse_product(raw_product_child)
        assert result.id == 1


# ---------------------------------------------------------------------------
# TestAggregateStock
# ---------------------------------------------------------------------------

class TestAggregateStock:
    def test_single_entry(self, client, raw_stock_entry):
        location_map = {2: "Fridge"}
        result = client.aggregate_stock([raw_stock_entry], location_map)
        assert len(result) == 1
        assert result[0].product_id == 1
        assert result[0].amount == 3.0
        assert result[0].location_name == "Fridge"

    def test_sums_multiple_batches_for_same_product(self, client, raw_stock_entry):
        second_batch = {**raw_stock_entry, "id": 2, "amount": 5, "stock_id": "abc"}
        location_map = {2: "Fridge"}
        result = client.aggregate_stock([raw_stock_entry, second_batch], location_map)
        assert len(result) == 1
        assert result[0].amount == 8.0

    def test_separate_entries_for_different_products(self, client, raw_stock_entry):
        other_product = {**raw_stock_entry, "id": 2, "product_id": 99, "amount": 1}
        location_map = {2: "Fridge"}
        result = client.aggregate_stock([raw_stock_entry, other_product], location_map)
        product_ids = {r.product_id for r in result}
        assert product_ids == {1, 99}

    def test_location_name_resolved_from_map(self, client, raw_stock_entry):
        location_map = {2: "Bar Shelf"}
        result = client.aggregate_stock([raw_stock_entry], location_map)
        assert result[0].location_name == "Bar Shelf"

    def test_location_name_none_when_location_id_missing_from_map(self, client, raw_stock_entry):
        result = client.aggregate_stock([raw_stock_entry], location_map={})
        assert result[0].location_name is None

    def test_location_name_none_when_entry_has_no_location_id(self, client, raw_stock_entry):
        raw_stock_entry["location_id"] = None
        result = client.aggregate_stock([raw_stock_entry], location_map={2: "Fridge"})
        assert result[0].location_name is None

    def test_location_taken_from_first_batch(self, client, raw_stock_entry):
        # Second batch is in a different location — first batch's location wins.
        second_batch = {**raw_stock_entry, "id": 2, "amount": 2, "location_id": 3, "stock_id": "abc"}
        location_map = {2: "Fridge", 3: "Bar Shelf"}
        result = client.aggregate_stock([raw_stock_entry, second_batch], location_map)
        assert result[0].location_name == "Fridge"

    def test_stock_unit_name_is_none(self, client, raw_stock_entry):
        # unit resolution (via quantity_units + product.qu_id_stock) not yet implemented
        result = client.aggregate_stock([raw_stock_entry], location_map={})
        assert result[0].stock_unit_name is None

    def test_empty_entries_returns_empty(self, client):
        result = client.aggregate_stock([], location_map={})
        assert result == []


# ---------------------------------------------------------------------------
# TestGetProductGroups
# ---------------------------------------------------------------------------

class TestGetProductGroups:
    @pytest.mark.asyncio
    async def test_returns_parsed_groups(self, client, raw_product_group):
        with patch.object(
            client, "_fetch_product_groups", new=AsyncMock(return_value=[raw_product_group])
        ):
            result = await client.get_product_groups()
        assert len(result) == 1
        assert result[0].name == "Alcohol"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(
            client, "_fetch_product_groups", new=AsyncMock(return_value=[])
        ):
            result = await client.get_product_groups()
        assert result == []


# ---------------------------------------------------------------------------
# TestGetProducts
# ---------------------------------------------------------------------------

class TestGetProducts:
    @pytest.mark.asyncio
    async def test_returns_parsed_products(self, client, raw_product_child, raw_product_parent):
        with patch.object(
            client,
            "_fetch_products",
            new=AsyncMock(return_value=[raw_product_child, raw_product_parent]),
        ):
            result = await client.get_products()
        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"High Noon | Pineapple", "High Noon"}

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(
            client, "_fetch_products", new=AsyncMock(return_value=[])
        ):
            result = await client.get_products()
        assert result == []


# ---------------------------------------------------------------------------
# TestGetStock
# ---------------------------------------------------------------------------

class TestGetStock:
    @pytest.mark.asyncio
    async def test_returns_aggregated_stock(self, client, raw_stock_entry, raw_location):
        with (
            patch.object(client, "_fetch_stock", new=AsyncMock(return_value=[raw_stock_entry])),
            patch.object(client, "_fetch_locations", new=AsyncMock(return_value=[raw_location])),
        ):
            result = await client.get_stock()
        assert len(result) == 1
        assert result[0].product_id == 1
        assert result[0].amount == 3.0
        assert result[0].location_name == "Fridge"

    @pytest.mark.asyncio
    async def test_empty_stock(self, client, raw_location):
        with (
            patch.object(client, "_fetch_stock", new=AsyncMock(return_value=[])),
            patch.object(client, "_fetch_locations", new=AsyncMock(return_value=[raw_location])),
        ):
            result = await client.get_stock()
        assert result == []
