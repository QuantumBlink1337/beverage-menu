from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from controllers.crafted_drinks import get_crafted_drinks, get_shopping_list, refresh
from models import CraftedDrinksResponse, ShoppingListResponse

router = APIRouter()


@router.get("/crafted_drinks", response_model=CraftedDrinksResponse)
async def crafted_drinks(
    host: bool = Query(False),
    tags: str | None = Query(None, description="Comma-separated tags to filter by, e.g. NYE,Summer"),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return await get_crafted_drinks(host_mode=host, tags=tag_list)


@router.get("/crafted_drinks/shopping_list", response_model=ShoppingListResponse)
async def shopping_list(
    tags: str = Query(..., description="Comma-separated tags, e.g. Kaiya"),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        raise HTTPException(status_code=422, detail="At least one tag is required")
    return await get_shopping_list(tag_list)


@router.post("/crafted_drinks/refresh", status_code=202)
async def refresh_crafted_drinks(background_tasks: BackgroundTasks):
    background_tasks.add_task(refresh)
    return {"status": "refresh queued"}
