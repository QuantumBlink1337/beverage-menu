import json
from datetime import datetime, timezone

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    DatabaseProxy,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    TextField,
)

database = DatabaseProxy()


def init_db(db) -> None:
    database.initialize(db)
    db.create_tables(
        [
            CacheStatus,
            GrocyProductGroup,
            GrocyProduct,
            GrocyStockEntry,
            CraftedDrink,
            CraftedDrinkIngredient,
            IngredientMapping,
        ],
        safe=True,
    )


class JSONListField(TextField):
    def db_value(self, value):
        return json.dumps(value or [])

    def python_value(self, value):
        return json.loads(value) if value else []


class BaseModel(Model):
    class Meta:
        database = database


_CACHE_KEY_RECIPES = "crafted_drinks"
_CACHE_KEY_GROCY = "grocy"


class CacheStatus(BaseModel):
    cache_key = CharField(primary_key=True)
    last_refreshed_at = CharField()  # ISO-8601 UTC

    @classmethod
    def _is_stale(cls, cache_key: str, ttl_seconds: float) -> bool:
        row = cls.get_or_none(cls.cache_key == cache_key)
        if row is None:
            return True
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row.last_refreshed_at)
        return age.total_seconds() > ttl_seconds

    @classmethod
    def _mark_refreshed(cls, cache_key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        (
            cls.insert(cache_key=cache_key, last_refreshed_at=now)
            .on_conflict(
                conflict_target=[cls.cache_key], preserve=[cls.last_refreshed_at]
            )
            .execute()
        )

    @classmethod
    def is_recipe_stale(cls, ttl_hours: int = 12) -> bool:
        return cls._is_stale(_CACHE_KEY_RECIPES, ttl_hours * 3600)

    @classmethod
    def is_grocy_stale(cls, ttl_minutes: int = 10) -> bool:
        return cls._is_stale(_CACHE_KEY_GROCY, ttl_minutes * 60)

    @classmethod
    def mark_recipe_refreshed(cls) -> None:
        cls._mark_refreshed(_CACHE_KEY_RECIPES)

    @classmethod
    def mark_grocy_refreshed(cls) -> None:
        cls._mark_refreshed(_CACHE_KEY_GROCY)


class GrocyProductGroup(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()

    @classmethod
    def upsert_all(cls, groups: list[dict]) -> None:
        with database.atomic():
            for data in groups:
                _, created = cls.get_or_create(id=data["id"], defaults=data)
                if not created:
                    cls.update(name=data["name"]).where(cls.id == data["id"]).execute()


class GrocyProduct(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()
    # Field names intentionally match Pydantic model keys so dicts pass through without remapping.
    # Peewee generates columns product_group_id and parent_product_id automatically.
    product_group = ForeignKeyField(GrocyProductGroup, null=True, backref="products")
    parent_product = ForeignKeyField("self", null=True, backref="children")
    no_own_stock = BooleanField(default=False)
    description = TextField(null=True)
    aliases = JSONListField(default=list)
    always_available = BooleanField(default=False)

    @classmethod
    def upsert_all(cls, products: list[dict]) -> None:
        # Insert parents before children to satisfy the self-referential FK.
        ordered = sorted(products, key=lambda p: p.get("parent_product_id") is not None)
        with database.atomic():
            for data in ordered:
                _, created = cls.get_or_create(id=data["id"], defaults=data)
                if not created:
                    cls.update(**{k: v for k, v in data.items() if k != "id"}).where(
                        cls.id == data["id"]
                    ).execute()


class GrocyStockEntry(BaseModel):
    # Peewee generates column product_id automatically.
    product = ForeignKeyField(GrocyProduct, backref="stock_entries")
    amount = FloatField()
    location_name = CharField(null=True)
    stock_unit_name = CharField(null=True)

    @classmethod
    def replace_all(cls, entries: list[dict]) -> None:
        with database.atomic():
            cls.delete().execute()
            if entries:
                cls.insert_many(entries).execute()


class CraftedDrink(BaseModel):
    notion_page_id = CharField(primary_key=True)
    name = CharField()
    glassware = CharField(null=True)
    classes = JSONListField(default=list)
    tags = JSONListField()
    equipment = JSONListField()
    method = TextField(null=True)
    notes = TextField(null=True)
    author = CharField(null=True)
    always_available = BooleanField(default=False)

    @classmethod
    def replace_all(cls, drinks_data: list[dict]) -> None:
        with database.atomic():
            CraftedDrinkIngredient.delete().execute()
            cls.delete().execute()
            for drink in drinks_data:
                ingredients = drink.pop("ingredients", [])
                record = cls.create(**drink)
                for ing in ingredients:
                    CraftedDrinkIngredient.create(drink=record, **ing)


class CraftedDrinkIngredient(BaseModel):
    drink = ForeignKeyField(CraftedDrink, backref="ingredients", on_delete="CASCADE")
    ingredient = CharField()
    amount = FloatField(null=True)
    unit = CharField(null=True)


class IngredientMapping(BaseModel):
    id = AutoField()
    notion_ingredient_name = CharField(unique=True)
    # Peewee generates column grocy_product_id automatically.
    grocy_product = ForeignKeyField(GrocyProduct, backref="mappings")
