import html
import os
import re
from collections import defaultdict

import httpx
from models import GrocyProduct, GrocyProductGroup, GrocyStockEntry


def _strip_html(text: str | None) -> str | None:
    """Grocy stores the description as rich-text HTML; flatten it to plain text."""
    if not text:
        return None
    plain = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", plain).strip() or None


class GrocyClient:
    def __init__(self):
        self.base_url = os.environ["GROCY_URL"].rstrip("/").removesuffix("/api")
        self.api_key = os.environ["GROCY_API_KEY"]
        self.headers = {"GROCY-API-KEY": self.api_key}
        # Grocy runs behind Tailscale Serve which uses a Tailscale-provisioned
        # certificate that Python's certifi bundle doesn't trust. Safe to skip
        # verification for a self-hosted internal service on a private Tailnet.
        self._http_client = httpx.AsyncClient(headers=self.headers, verify=False)

    # ---------------------------------------------------------------------------
    # Private fetch methods — return raw Grocy response dicts
    # ---------------------------------------------------------------------------

    async def _fetch_product_groups(self) -> list[dict]:
        response = await self._http_client.get(
            f"{self.base_url}/api/objects/product_groups"
        )
        response.raise_for_status()
        return response.json()

    async def _fetch_products(self) -> list[dict]:
        response = await self._http_client.get(f"{self.base_url}/api/objects/products")
        response.raise_for_status()
        return response.json()

    async def _fetch_stock(self) -> list[dict]:
        response = await self._http_client.get(f"{self.base_url}/api/objects/stock")
        response.raise_for_status()
        return response.json()

    async def _fetch_locations(self) -> list[dict]:
        response = await self._http_client.get(f"{self.base_url}/api/objects/locations")
        response.raise_for_status()
        return response.json()

    async def _fetch_quantity_units(self) -> list[dict]:
        response = await self._http_client.get(
            f"{self.base_url}/api/objects/quantity_units"
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
        stock_unit_name is resolved by cross-referencing each product's
        qu_id_stock against the /objects/quantity_units table.
        """
        raw_stock, raw_locations, raw_products, raw_units = (
            await self._fetch_stock(),
            await self._fetch_locations(),
            await self._fetch_products(),
            await self._fetch_quantity_units(),
        )
        location_map = {loc["id"]: loc["name"] for loc in raw_locations}
        unit_name_by_id = {u["id"]: u["name"] for u in raw_units}
        product_unit_map = {
            p["id"]: unit_name_by_id.get(p.get("qu_id_stock")) for p in raw_products
        }
        return self.aggregate_stock(raw_stock, location_map, product_unit_map)

    # ---------------------------------------------------------------------------
    # Parsing helpers
    # ---------------------------------------------------------------------------

    def parse_product_group(self, raw: dict) -> GrocyProductGroup:
        return GrocyProductGroup(id=raw["id"], name=raw["name"])

    def parse_product(self, raw: dict) -> GrocyProduct:
        uf = raw["userfields"] or {}
        raw_aliases = uf.get("notion_aliases") or ""
        aliases = [a.strip() for a in re.split(r"[\n,]", raw_aliases) if a.strip()]
        return GrocyProduct(
            id=raw["id"],
            name=raw["name"].strip(),
            product_group_id=raw.get("product_group_id"),
            parent_product_id=raw.get("parent_product_id"),
            no_own_stock=bool(raw.get("no_own_stock", 0)),
            description=_strip_html(raw.get("description")),
            aliases=aliases,
            always_available=uf.get("always_available") in ("1", 1, True),
        )

    def aggregate_stock(
        self,
        entries: list[dict],
        location_map: dict[int, str],
        product_unit_map: dict[int, str | None] | None = None,
    ) -> list[GrocyStockEntry]:
        """Aggregate raw batch entries into one GrocyStockEntry per product.

        Amount is summed across all batches. location_name is taken from the
        first batch's location_id; if a product is split across multiple
        locations, only the first is recorded (sufficient for display purposes).
        stock_unit_name is looked up from product_unit_map (product_id → unit
        name) when provided.
        """
        product_unit_map = product_unit_map or {}
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
                stock_unit_name=product_unit_map.get(pid),
            )
            for pid, amount in totals.items()
        ]
