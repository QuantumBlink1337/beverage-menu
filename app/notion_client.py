import httpx
import os

from models import NotionCraftedDrinkProperties, NotionIngredientRow, NotionEquipmentRow

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

    async def get_crafted_drinks(self) -> list[dict]:
        """Query the crafted drinks database. Returns raw Notion page objects."""
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

    async def get_page_blocks(self, page_id: str) -> list[dict]:
        """Fetch top-level blocks for a page. Used to locate the embedded ingredients database."""
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

    async def get_database_rows(self, database_id: str) -> list[dict]:
        """Query an embedded database (e.g. ingredients). Returns raw Notion page objects."""
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
    # Parsing helpers
    # ---------------------------------------------------------------------------

    def parse_drink_properties(self, page: dict) -> NotionCraftedDrinkProperties:
        """Parse a raw Notion page object into NotionCraftedDrinkProperties."""
        props = page["properties"]
        glassware_select = props["Glassware"]["select"]
        return NotionCraftedDrinkProperties(
            name=props["Name"]["title"][0]["plain_text"],
            glassware=glassware_select["name"] if glassware_select else None,
            tags=[t["name"] for t in props["Tags"]["multi_select"]],
            notes="".join(r["plain_text"] for r in props["Notes"]["rich_text"]) or None,
            author="".join(r["plain_text"] for r in props["Author"]["rich_text"]) or None,
        )

    def parse_blocks(self, blocks: list[dict]) -> tuple[dict[str, str], str | None]:
        """Extract child database IDs and method steps from a page's block list.

        Returns:
            db_ids: dict mapping database title ("Ingredients", "Equipment") to block ID
            method: numbered steps joined as a single string, or None if absent
        """
        db_ids: dict[str, str] = {}
        steps: list[str] = []

        for block in blocks:
            if block["type"] == "child_database":
                title = block["child_database"]["title"]
                db_ids[title] = block["id"]
            elif block["type"] == "numbered_list_item":
                step = block["numbered_list_item"]["rich_text"][0]["plain_text"]
                steps.append(step)

        method = "\n".join(steps) or None
        return db_ids, method

    def parse_ingredient_row(self, row: dict) -> NotionIngredientRow:
        """Parse a raw Notion page object from the Ingredients database."""
        props = row["properties"]
        unit_select = props["Unit"]["select"]
        return NotionIngredientRow(
            ingredient=props["Ingredient"]["title"][0]["plain_text"],
            amount=props["Amount"]["number"],
            unit=unit_select["name"] if unit_select else None,
        )

    def parse_equipment_row(self, row: dict) -> NotionEquipmentRow:
        """Parse a raw Notion page object from the Equipment database."""
        return NotionEquipmentRow(
            name=row["properties"]["Name"]["title"][0]["plain_text"],
        )
