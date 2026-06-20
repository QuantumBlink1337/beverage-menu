from collections import defaultdict

from db import CacheStatus, GrocyProduct, GrocyProductGroup, GrocyStockEntry
from grocy_client import GrocyClient
from models import (
    BeverageGroup,
    BeveragesResponse,
    GrocyProduct as GrocyProductModel,
    Product,
)


def _variant_name(name: str) -> str:
    """Return the variant part of 'Brand | Variant', or the full name if no separator."""
    parts = name.split(" | ", 1)
    return parts[1] if len(parts) == 2 else name


async def get_beverages(host_mode: bool = False) -> BeveragesResponse:
    if CacheStatus.is_grocy_stale():
        await _refresh()
    return _build_response(host_mode)


def _drop_dangling_refs(
    products: list[GrocyProductModel],
    group_ids: set[int],
    product_ids: set[int],
) -> None:
    """Null out FK references to groups/parents not present in the fetched data.

    A stale Grocy edit (e.g. a product still assigned to a since-deleted group) would
    otherwise violate the foreign-key constraint and fail the *entire* refresh on a cold
    DB. Nulling the dangling ref degrades that product to the 'Unknown' group instead of
    taking down the whole beverages endpoint.
    """
    for p in products:
        if p.product_group_id is not None and p.product_group_id not in group_ids:
            p.product_group_id = None
        if p.parent_product_id is not None and p.parent_product_id not in product_ids:
            p.parent_product_id = None


async def _refresh() -> None:
    client = GrocyClient()
    groups = await client.get_product_groups()
    products = await client.get_products()
    stock = await client.get_stock()

    GrocyProductGroup.upsert_all([g.model_dump() for g in groups])
    _drop_dangling_refs(products, {g.id for g in groups}, {p.id for p in products})
    GrocyProduct.upsert_all([p.model_dump() for p in products])
    GrocyStockEntry.replace_all([s.model_dump() for s in stock])
    CacheStatus.mark_grocy_refreshed()


def _build_response(host_mode: bool) -> BeveragesResponse:
    # Index in-stock entries by product_id.
    stock_map: dict[int, GrocyStockEntry] = {}
    for entry in GrocyStockEntry.select():
        if entry.amount > 0:
            stock_map[entry.product_id] = entry

    all_products = {p.id: p for p in GrocyProduct.select()}
    all_groups = {g.id: g for g in GrocyProductGroup.select()}

    # Partition in-stock products into standalone products and children.
    children_by_parent: dict[int, list] = defaultdict(list)
    standalone: list = []

    for pid in stock_map:
        product = all_products.get(pid)
        if product is None:
            continue
        if product.parent_product_id:
            children_by_parent[product.parent_product_id].append(product)
        else:
            standalone.append(product)

    # Build Product response models, grouped by product_group_id.
    products_in_group: dict[int | None, list[Product]] = defaultdict(list)

    for product in standalone:
        entry = stock_map[product.id]
        products_in_group[product.product_group_id].append(
            Product(
                id=product.id,
                name=product.name,
                amount=entry.amount,
                unit=entry.stock_unit_name,
                location=entry.location_name,
                description=product.description,
            )
        )

    for parent_id, children in children_by_parent.items():
        parent = all_products.get(parent_id)
        if parent is None:
            continue
        child_products = [
            Product(
                id=child.id,
                name=_variant_name(child.name),
                amount=stock_map[child.id].amount,
                unit=stock_map[child.id].stock_unit_name,
                location=stock_map[child.id].location_name,
            )
            for child in sorted(children, key=lambda c: c.name)
        ]
        products_in_group[parent.product_group_id].append(
            Product(
                id=parent.id,
                name=parent.name,
                description=parent.description,
                children=child_products,
            )
        )

    # Assemble BeverageGroup list.
    groups = []
    for group_id, products in products_in_group.items():
        group = all_groups.get(group_id)
        group_name = group.name if group else "Unknown"
        groups.append(
            BeverageGroup(
                name=group_name,
                products=sorted(products, key=lambda p: p.name),
            )
        )

    groups.sort(key=lambda g: g.name)
    return BeveragesResponse(groups=groups)
