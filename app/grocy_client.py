import os
from collections import defaultdict

import httpx
from models import GrocyProduct, GrocyProductGroup, GrocyStockEntry


class GrocyClient:
    def __init__(self):
        self.base_url = os.environ["GROCY_URL"].rstrip("/")
        self.api_key = os.environ["GROCY_API_KEY"]
        self.headers = {"GROCY-API-KEY": self.api_key}

    # ---------------------------------------------------------------------------
    # Private fetch methods — return raw Grocy response dicts
    # ---------------------------------------------------------------------------

    async def _fetch_product_groups(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/objects/product_groups",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def _fetch_products(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/objects/products",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def _fetch_stock(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/objects/stock",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def _fetch_locations(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/objects/locations",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    # ---------------------------------------------------------------------------
    # Public methods — return typed, parsed objects
    # ---------------------------------------------------------------------------

    async def get_product_groups(self) -> list[GrocyProductGroup]:
        raw = await self._fetch_product_groups()
        return [self.parse_product_group(r) for r in raw]

    async def get_products(self) -> list[GrocyProduct]:
        raw = await self._fetch_products()
        return [self.parse_product(r) for r in raw]

    async def get_stock(self) -> list[GrocyStockEntry]:
        """Return one aggregated GrocyStockEntry per product (summed amount).

        /api/objects/stock returns individual batch entries — a product purchased
        twice has two rows. We aggregate here so the DB layer sees one row per
        product, matching the replace_all() semantics.

        location_name is resolved via a /objects/locations lookup.
        stock_unit_name is not yet resolved (requires /objects/quantity_units
        cross-referenced with product.qu_id_stock — follow-up task).
        """
        raw_stock, raw_locations = (
            await self._fetch_stock(),
            await self._fetch_locations(),
        )
        location_map = {loc["id"]: loc["name"] for loc in raw_locations}
        return self.aggregate_stock(raw_stock, location_map)

    # ---------------------------------------------------------------------------
    # Parsing helpers
    # ---------------------------------------------------------------------------

    def parse_product_group(self, raw: dict) -> GrocyProductGroup:
        return GrocyProductGroup(id=raw["id"], name=raw["name"])

    def parse_product(self, raw: dict) -> GrocyProduct:
        return GrocyProduct(
            id=raw["id"],
            name=raw["name"].strip(),
            product_group_id=raw.get("product_group_id"),
            parent_product_id=raw.get("parent_product_id"),
            no_own_stock=bool(raw.get("no_own_stock", 0)),
            description=raw.get("description") or None,
        )

    def aggregate_stock(
        self, entries: list[dict], location_map: dict[int, str]
    ) -> list[GrocyStockEntry]:
        """Aggregate raw batch entries into one GrocyStockEntry per product.

        Amount is summed across all batches. location_name is taken from the
        first batch's location_id; if a product is split across multiple
        locations, only the first is recorded (sufficient for display purposes).
        """
        totals: dict[int, float] = defaultdict(float)
        first_location: dict[int, int | None] = {}

        for entry in entries:
            pid = entry["product_id"]
            totals[pid] += float(entry["amount"])
            if pid not in first_location:
                first_location[pid] = entry.get("location_id")

        return [
            GrocyStockEntry(
                product_id=pid,
                amount=amount,
                location_name=location_map.get(first_location[pid])
                if first_location.get(pid) is not None
                else None,
            )
            for pid, amount in totals.items()
        ]
