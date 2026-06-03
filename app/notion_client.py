import os

import httpx
from models import NotionCraftedDrinkProperties, NotionEquipmentRow, NotionIngredientRow, NotionPageContent

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    def __init__(self):
        self.api_key = os.environ["NOTION_API_KEY"]
        self.database_id = os.environ["NOTION_CRAFTED_DRINKS_DB_ID"]
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ---------------------------------------------------------------------------
    # Private fetch methods — return raw Notion response dicts
    # ---------------------------------------------------------------------------

    async def _fetch_crafted_drinks(self) -> list[dict]:
        results = []
        payload: dict = {}

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.post(
                    f"{NOTION_API_BASE}/databases/{self.database_id}/query",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                results.extend(data["results"])

                if not data.get("has_more"):
                    break
                payload["start_cursor"] = data["next_cursor"]

        return results

    async def _fetch_page_blocks(self, page_id: str) -> list[dict]:
        results = []
        url = f"{NOTION_API_BASE}/blocks/{page_id}/children"
        params: dict = {}

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                results.extend(data["results"])

                if not data.get("has_more"):
                    break
                params["start_cursor"] = data["next_cursor"]

        return results

    async def _fetch_database_rows(self, database_id: str) -> list[dict]:
        results = []
        payload: dict = {}

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.post(
                    f"{NOTION_API_BASE}/databases/{database_id}/query",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                results.extend(data["results"])

                if not data.get("has_more"):
                    break
                payload["start_cursor"] = data["next_cursor"]

        return results

    # ---------------------------------------------------------------------------
    # Public methods — return typed, parsed objects
    # ---------------------------------------------------------------------------

    async def get_crafted_drinks(self) -> list[NotionCraftedDrinkProperties]:
        """Return all crafted drink pages as parsed properties, excluding the template."""
        pages = await self._fetch_crafted_drinks()
        return [
            self.parse_drink_properties(page)
            for page in pages
            if page["properties"]["Name"]["title"][0]["plain_text"] not in "Template"
        ]

    async def get_page_blocks(self, page_id: str) -> NotionPageContent:
        """Return child database IDs by title and the method string for a drink page."""
        blocks = await self._fetch_page_blocks(page_id)
        return self.parse_blocks(blocks)

    async def get_ingredient_rows(self, database_id: str) -> list[NotionIngredientRow]:
        """Return parsed ingredient rows for an embedded Ingredients database."""
        rows = await self._fetch_database_rows(database_id)
        return [self.parse_ingredient_row(row) for row in rows]

    async def get_equipment_rows(self, database_id: str) -> list[NotionEquipmentRow]:
        """Return parsed equipment rows for an embedded Equipment database."""
        rows = await self._fetch_database_rows(database_id)
        return [self.parse_equipment_row(row) for row in rows]

    # ---------------------------------------------------------------------------
    # Parsing helpers
    # ---------------------------------------------------------------------------

    def parse_drink_properties(self, page: dict) -> NotionCraftedDrinkProperties:
        properties = page["properties"]
        glassware_select = properties["Glassware"]["select"]
        return NotionCraftedDrinkProperties(
            page_id=page["id"],
            name=properties["Name"]["title"][0]["plain_text"],
            glassware=glassware_select["name"] if glassware_select else None,
            tags=[t["name"] for t in properties["Tags"]["multi_select"]],
            notes="".join(r["plain_text"] for r in properties["Notes"]["rich_text"])
            or None,
            author="".join(r["plain_text"] for r in properties["Author"]["rich_text"])
            or None,
        )

    def parse_blocks(self, blocks: list[dict]) -> NotionPageContent:
        """Extract child database IDs and method steps from a page's block list."""
        db_ids: dict[str, str] = {}
        steps: list[str] = []

        for block in blocks:
            if block["type"] == "child_database":
                title = block["child_database"]["title"]
                db_ids[title] = block["id"]
            elif block["type"] == "numbered_list_item":
                step = block["numbered_list_item"]["rich_text"][0]["plain_text"]
                steps.append(step)

        return NotionPageContent(
            db_ids=db_ids,
            method="\n".join(steps) or None,
        )

    def parse_ingredient_row(self, row: dict) -> NotionIngredientRow:
        props = row["properties"]
        unit_select = props["Unit"]["select"]
        return NotionIngredientRow(
            ingredient=props["Ingredient"]["title"][0]["plain_text"],
            amount=props["Amount"]["number"],
            unit=unit_select["name"] if unit_select else None,
        )

    def parse_equipment_row(self, row: dict) -> NotionEquipmentRow:
        return NotionEquipmentRow(
            name=row["properties"]["Name"]["title"][0]["plain_text"],
        )
