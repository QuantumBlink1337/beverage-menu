from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class Tag(BaseModel):
    name: str
    color: str = "default"  # Notion multi-select option color


# ---------------------------------------------------------------------------
# Grocy — internal parsing models
# ---------------------------------------------------------------------------

class GrocyProductGroup(BaseModel):
    id: int
    name: str


class GrocyProduct(BaseModel):
    id: int
    name: str
    product_group_id: int | None = None
    parent_product_id: int | None = None
    no_own_stock: bool = False
    description: str | None = None


class GrocyStockEntry(BaseModel):
    product_id: int
    amount: float
    location_name: str | None = None
    stock_unit_name: str | None = None


# ---------------------------------------------------------------------------
# API response models — Beverages
# ---------------------------------------------------------------------------

class Product(BaseModel):
    id: int
    name: str
    amount: float | None = None       # None for parent products
    unit: str | None = None
    location: str | None = None
    description: str | None = None     # guest-visible blurb (from Grocy's description field)
    children: list["Product"] = []    # empty for standalone products


class BeverageGroup(BaseModel):
    name: str
    products: list[Product]


class BeveragesResponse(BaseModel):
    groups: list[BeverageGroup]


# ---------------------------------------------------------------------------
# Notion — internal parsing models
# ---------------------------------------------------------------------------

class NotionCraftedDrinkProperties(BaseModel):
    page_id: str
    name: str
    glassware: str | None = None
    tags: list[Tag] = []
    equipment: list[str] = []  # multi-select property on the drink page
    notes: str | None = None   # maps to "Notes" property — host mode only
    author: str | None = None


class NotionPageContent(BaseModel):
    db_ids: dict[str, str]   # e.g. {"Ingredients": "..."}
    method: str | None = None


class NotionIngredientRow(BaseModel):
    ingredient: str
    amount: float | None = None
    unit: str | None = None  # select: "oz", "piece" (will grow)


# ---------------------------------------------------------------------------
# API response models — Crafted Drinks
# ---------------------------------------------------------------------------

class IngredientDetail(BaseModel):
    ingredient: str
    amount: float | None = None
    unit: str | None = None
    in_stock: bool
    matched: bool


class CraftedDrink(BaseModel):
    id: str  # Notion page ID
    name: str
    glassware: str | None = None
    tags: list[Tag] = []
    method: str | None = None
    available: bool
    ingredients: list[IngredientDetail] = []
    equipment: list[str] = []
    host_notes: str | None = None          # host mode only
    author: str | None = None              # host mode only
    unmatched_ingredients: list[str] = []  # host mode only


class CraftedDrinksResponse(BaseModel):
    crafted_drinks: list[CraftedDrink]


# ---------------------------------------------------------------------------
# API response models — Ingredient Mappings (host mode only)
# ---------------------------------------------------------------------------

class MappingEntry(BaseModel):
    id: int
    notion_ingredient_name: str
    grocy_product_id: int


class MappingsResponse(BaseModel):
    mappings: list[MappingEntry]
    unmatched: list[str]  # ingredient names present in Notion with no mapping row


class CreateMappingRequest(BaseModel):
    notion_ingredient_name: str
    grocy_product_id: int
