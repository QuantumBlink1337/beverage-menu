from fastapi import APIRouter, BackgroundTasks, Query

from controllers.crafted_drinks import get_crafted_drinks, refresh
from models import CraftedDrinksResponse

router = APIRouter()


@router.get("/crafted_drinks", response_model=CraftedDrinksResponse)
async def crafted_drinks(
    host: bool = Query(False),
    tags: str | None = Query(None, description="Comma-separated tags to filter by, e.g. NYE,Summer"),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return await get_crafted_drinks(host_mode=host, tags=tag_list)


@router.post("/crafted_drinks/refresh", status_code=202)
async def refresh_crafted_drinks(background_tasks: BackgroundTasks):
    background_tasks.add_task(refresh)
    return {"status": "refresh queued"}
