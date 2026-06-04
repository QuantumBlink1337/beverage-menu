import asyncio

from dotenv import load_dotenv
from grocy_client import GrocyClient

load_dotenv()


async def main():
    client = GrocyClient()

    print("--- Product Groups ---")
    groups = await client.get_product_groups()
    for g in groups:
        print(g)

    print("\n--- Products ---")
    products = await client.get_products()
    for p in products:
        print(p)

    print("\n--- Stock (aggregated) ---")
    stock = await client.get_stock()
    for s in stock:
        print(s)


asyncio.run(main())
