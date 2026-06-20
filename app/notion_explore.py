import asyncio
import json

from dotenv import load_dotenv
from notion_client import NotionClient

load_dotenv()

# Campfire page ID from the API response
PAGE_ID = "3749babc-c3ed-802f-bb22-e35f5105504b"


async def main():
    client = NotionClient()

    print("--- Raw Blocks ---")
    blocks = await client._fetch_page_blocks(PAGE_ID)
    print(json.dumps(blocks, indent=2))


asyncio.run(main())
