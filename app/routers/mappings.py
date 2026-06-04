from fastapi import APIRouter, HTTPException

from db import CraftedDrinkIngredient, IngredientMapping
from models import CreateMappingRequest, MappingEntry, MappingsResponse

router = APIRouter()


@router.get("/mappings", response_model=MappingsResponse)
def get_mappings():
    mappings = [
        MappingEntry(
            id=m.id,
            notion_ingredient_name=m.notion_ingredient_name,
            grocy_product_id=m.grocy_product_id,
        )
        for m in IngredientMapping.select()
    ]

    mapped_names = {m.notion_ingredient_name for m in mappings}
    all_names = {ing.ingredient for ing in CraftedDrinkIngredient.select()}
    unmatched = sorted(all_names - mapped_names)

    return MappingsResponse(mappings=mappings, unmatched=unmatched)


@router.post("/mappings", response_model=MappingEntry, status_code=201)
def create_mapping(body: CreateMappingRequest):
    mapping = IngredientMapping.create(
        notion_ingredient_name=body.notion_ingredient_name,
        grocy_product_id=body.grocy_product_id,
    )
    return MappingEntry(
        id=mapping.id,
        notion_ingredient_name=mapping.notion_ingredient_name,
        grocy_product_id=mapping.grocy_product_id,
    )


@router.delete("/mappings/{mapping_id}", status_code=204)
def delete_mapping(mapping_id: int):
    deleted = IngredientMapping.delete().where(IngredientMapping.id == mapping_id).execute()
    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found")
