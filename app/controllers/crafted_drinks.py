import asyncio
from collections import defaultdict

from db import (
    CacheStatus,
    GrocyProduct,
    GrocyProductGroup,
    GrocyStockEntry,
    IngredientMapping,
)
from db import (
    CraftedDrink as DBCraftedDrink,
)
from models import (
    CraftedDrink,
    CraftedDrinksResponse,
    IngredientDetail,
    ShoppingListItem,
    ShoppingListResponse,
)
from notion_client import NotionClient

# Notion API rate limit: 3 requests/second.
_NOTION_SEMAPHORE = asyncio.Semaphore(3)


def _norm(s: str) -> str:
    """Normalize a name for case/whitespace-insensitive ingredient matching."""
    return s.strip().lower()


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


def _build_matcher():
    """Return resolve(ingredient_name) -> (matched, in_stock) built from current Grocy data."""
    products = list(GrocyProduct.select())

    # Build a stock map of in-stock product IDs.
    in_stock_ids: set[int] = {
        e.product_id for e in GrocyStockEntry.select() if e.amount > 0
    }
    # some stuff might always be available so we dont need to look at quantity for those
    in_stock_ids |= {p.id for p in products if p.always_available}

    # TODO clean up and retire ingredient map
    ingredient_map: dict[str, int] = {
        _norm(m.notion_ingredient_name): m.grocy_product_id
        for m in IngredientMapping.select()
    }
    # look at grocy aliases first before use automatch
    alias_map: dict[str, int] = {}
    for p in products:
        for alias in p.aliases:
            alias_map[_norm(alias)] = p.id

    # Fallback: auto-match when a Notion ingredient name equals a Grocy product
    # name.
    grocy_by_name: dict[str, int] = {_norm(p.name): p.id for p in products}

    # Group fallback: a generic ingredient (e.g. "Bourbon") matches any product in
    # the group of that name, and is in stock if ANY of those products is.
    group_name_by_id = {g.id: g.name for g in GrocyProductGroup.select()}
    group_products: dict[str, list[int]] = defaultdict(list)
    for p in products:
        if p.product_group_id in group_name_by_id:
            group_products[_norm(group_name_by_id[p.product_group_id])].append(p.id)

    def resolve(name: str) -> tuple[bool, bool]:
        # Precedence: alias → ingredient map → exact product name → product group.
        # Matching is case/whitespace-insensitive (normalized key).
        key = _norm(name)
        pid = alias_map.get(key)
        if pid is None:
            pid = ingredient_map.get(key)  # fallback to ingredient map
        if pid is None:
            pid = grocy_by_name.get(key)

        if pid is not None:  # matched a specific bottle
            return True, pid in in_stock_ids
        if key in group_products:  # matched a group → any bottle counts
            return True, any(p in in_stock_ids for p in group_products[key])
        return False, False

    return resolve


def _filter_by_tags(db_drinks, tags: list[str] | None):
    """Keep drinks whose tags intersect the filter (no filter → all drinks)."""
    if not tags:
        return db_drinks
    tag_set = set(tags)
    return [d for d in db_drinks if tag_set & {t["name"] for t in d.tags}]


def _build_response(
    host_mode: bool,
    tags: list[str] | None = None,
) -> CraftedDrinksResponse:
    resolve = _build_matcher()

    db_drinks = list(DBCraftedDrink.select())

    db_drinks = _filter_by_tags(db_drinks, tags)

    crafted_drinks = []
    for db_drink in db_drinks:
        ingredients = []
        unmatched: list[str] = []
        all_matched_in_stock = True

        for ing in db_drink.ingredients:
            matched, in_stock = resolve(ing.ingredient)

            if not matched:
                unmatched.append(ing.ingredient)
            elif not in_stock:
                all_matched_in_stock = False

            ingredients.append(
                IngredientDetail(
                    ingredient=ing.ingredient,
                    amount=ing.amount,
                    unit=ing.unit,
                    in_stock=in_stock,
                    matched=matched,
                )
            )

        crafted_drinks.append(
            CraftedDrink(
                id=db_drink.notion_page_id,
                name=db_drink.name,
                glassware=db_drink.glassware,
                classes=db_drink.classes,
                tags=db_drink.tags,
                method=db_drink.method,
                available=all_matched_in_stock and not unmatched,
                ingredients=ingredients,
                equipment=db_drink.equipment,
                host_notes=db_drink.notes if host_mode else None,
                author=db_drink.author if host_mode else None,
                unmatched_ingredients=unmatched if host_mode else [],
            )
        )

    return CraftedDrinksResponse(crafted_drinks=crafted_drinks)


async def get_shopping_list(tags: list[str]) -> ShoppingListResponse:
    """Ingredients missing (out of stock or unmatched) across drinks with any of `tags`."""
    if CacheStatus.is_recipe_stale():
        await refresh()
    resolve = _build_matcher()
    drinks = _filter_by_tags(list(DBCraftedDrink.select()), tags)

    # Dedupe on the normalized name; remember which drinks need each ingredient.
    items: dict[str, ShoppingListItem] = {}
    for drink in drinks:
        for ing in drink.ingredients:
            matched, in_stock = resolve(ing.ingredient)
            if matched and in_stock:
                continue
            item = items.setdefault(
                _norm(ing.ingredient),
                ShoppingListItem(
                    ingredient=ing.ingredient.strip(),
                    status="out_of_stock" if matched else "unmatched",
                ),
            )
            if drink.name not in item.drinks:
                item.drinks.append(drink.name)

    return ShoppingListResponse(
        tags=tags,
        drink_count=len(drinks),
        items=sorted(items.values(), key=lambda i: i.ingredient.lower()),
    )
