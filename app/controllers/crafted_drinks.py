import asyncio

from db import (
    CacheStatus,
    CraftedDrink as DBCraftedDrink,
    GrocyProduct,
    GrocyStockEntry,
    IngredientMapping,
)
from models import CraftedDrink, CraftedDrinksResponse, IngredientDetail
from notion_client import NotionClient

# Notion API rate limit: 3 requests/second.
_NOTION_SEMAPHORE = asyncio.Semaphore(3)


async def get_crafted_drinks(
    host_mode: bool = False,
    tags: list[str] | None = None,
) -> CraftedDrinksResponse:
    if CacheStatus.is_recipe_stale():
        await refresh()
    return _build_response(host_mode=host_mode, tags=tags)


async def refresh() -> None:
    """Fetch all crafted drinks from Notion and replace the DB cache."""
    client = NotionClient()
    drinks = await client.get_crafted_drinks()

    async def fetch_drink_data(drink):
        async with _NOTION_SEMAPHORE:
            content = await client.get_page_blocks(drink.page_id)

        ingredients = []
        if "Ingredients" in content.db_ids:
            async with _NOTION_SEMAPHORE:
                rows = await client.get_ingredient_rows(content.db_ids["Ingredients"])
            ingredients = [r.model_dump() for r in rows]

        data = drink.model_dump()
        data["notion_page_id"] = data.pop("page_id")
        data["method"] = content.method
        data["ingredients"] = ingredients
        return data

    drinks_data = await asyncio.gather(*[fetch_drink_data(d) for d in drinks])
    DBCraftedDrink.replace_all(list(drinks_data))
    CacheStatus.mark_recipe_refreshed()


def _build_response(
    host_mode: bool,
    tags: list[str] | None = None,
) -> CraftedDrinksResponse:
    # Build a stock map of in-stock product IDs.
    in_stock_ids: set[int] = {
        e.product_id for e in GrocyStockEntry.select() if e.amount > 0
    }

    ingredient_map: dict[str, int] = {
        m.notion_ingredient_name: m.grocy_product_id
        for m in IngredientMapping.select()
    }

    # Fallback: auto-match when a Notion ingredient name exactly equals a Grocy
    # product name. The explicit mapping above always takes precedence.
    grocy_by_name: dict[str, int] = {
        p.name: p.id for p in GrocyProduct.select()
    }

    db_drinks = list(DBCraftedDrink.select())

    # Filter by tags if provided — include drinks whose tags intersect the filter.
    if tags:
        tag_set = set(tags)
        db_drinks = [d for d in db_drinks if tag_set & set(d.tags)]

    crafted_drinks = []
    for db_drink in db_drinks:
        ingredients = []
        unmatched: list[str] = []
        all_matched_in_stock = True

        for ing in db_drink.ingredients:
            # Explicit mapping wins; fall back to an exact Grocy product-name match.
            grocy_product_id = ingredient_map.get(ing.ingredient)
            if grocy_product_id is None:
                grocy_product_id = grocy_by_name.get(ing.ingredient)
            if grocy_product_id is None:
                unmatched.append(ing.ingredient)
                ingredients.append(IngredientDetail(
                    ingredient=ing.ingredient,
                    amount=ing.amount,
                    unit=ing.unit,
                    in_stock=False,
                    matched=False,
                ))
            else:
                in_stock = grocy_product_id in in_stock_ids
                if not in_stock:
                    all_matched_in_stock = False
                ingredients.append(IngredientDetail(
                    ingredient=ing.ingredient,
                    amount=ing.amount,
                    unit=ing.unit,
                    in_stock=in_stock,
                    matched=True,
                ))

        crafted_drinks.append(CraftedDrink(
            id=db_drink.notion_page_id,
            name=db_drink.name,
            glassware=db_drink.glassware,
            tags=db_drink.tags,
            method=db_drink.method,
            available=all_matched_in_stock,
            ingredients=ingredients,
            equipment=db_drink.equipment,
            host_notes=db_drink.notes if host_mode else None,
            author=db_drink.author if host_mode else None,
            unmatched_ingredients=unmatched if host_mode else [],
        ))

    return CraftedDrinksResponse(crafted_drinks=crafted_drinks)
