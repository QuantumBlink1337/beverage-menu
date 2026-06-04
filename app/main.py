# import asyncio

# from dotenv import load_dotenv
# from notion_client import NotionClient

# load_dotenv()


# async def main():
#     client = NotionClient()

#     print("--- Crafted Drinks ---")
#     drinks = await client.get_crafted_drinks()
#     for drink in drinks:
#         print(drink)

#     if not drinks:
#         print("No drinks returned.")
#         return

#     print("\n--- Page Blocks (first drink) ---")
#     content = await client.get_page_blocks(drinks[0].page_id)
#     print(content)

#     print("\n--- Ingredients ---")
#     if "Ingredients" in content.db_ids:
#         ingredients = await client.get_ingredient_rows(content.db_ids["Ingredients"])
#         for ingredient in ingredients:
#             print(ingredient)
#     else:
#         print("No Ingredients database found.")


# asyncio.run(main())

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from peewee import SqliteDatabase

from db import CacheStatus, init_db

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SqliteDatabase(
        os.getenv("DB_PATH", "beverage.db"),
        pragmas={"foreign_keys": 1},
    )
    init_db(db)

    # Populate recipe cache before serving the first request if it's empty or stale.
    if CacheStatus.is_recipe_stale():
        from controllers.crafted_drinks import refresh
        await refresh()

    yield

    db.close()


app = FastAPI(lifespan=lifespan)

from routers import beverages, crafted_drinks, mappings
app.include_router(beverages.router, prefix="/api")
app.include_router(crafted_drinks.router, prefix="/api")
app.include_router(mappings.router, prefix="/api")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
