import asyncio

from dotenv import load_dotenv
from notion_client import NotionClient

load_dotenv()


async def main():
    client = NotionClient()

    print("--- Crafted Drinks ---")
    drinks = await client.get_crafted_drinks()
    for drink in drinks:
        print(drink)

    if not drinks:
        print("No drinks returned.")
        return

    print("\n--- Page Blocks (first drink) ---")
    content = await client.get_page_blocks(drinks[0].page_id)
    print(content)

    print("\n--- Ingredients ---")
    if "Ingredients" in content.db_ids:
        ingredients = await client.get_ingredient_rows(content.db_ids["Ingredients"])
        for ingredient in ingredients:
            print(ingredient)
    else:
        print("No Ingredients database found.")

    print("\n--- Equipment ---")
    if "Equipment" in content.db_ids:
        equipment = await client.get_equipment_rows(content.db_ids["Equipment"])
        for item in equipment:
            print(item)
    else:
        print("No Equipment database found.")


asyncio.run(main())
