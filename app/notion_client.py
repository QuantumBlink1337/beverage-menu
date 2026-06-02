import httpx
import os

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
