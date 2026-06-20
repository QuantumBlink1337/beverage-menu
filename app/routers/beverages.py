from fastapi import APIRouter, BackgroundTasks, Query

from controllers.beverages import _refresh, get_beverages
from models import BeveragesResponse

router = APIRouter()


@router.get("/beverages", response_model=BeveragesResponse)
async def beverages(host: bool = Query(False)):
    return await get_beverages(host_mode=host)


@router.post("/beverages/refresh", status_code=202)
async def refresh_beverages(background_tasks: BackgroundTasks):
    """Force a Grocy re-pull regardless of the cache TTL (host 'Refresh data' button)."""
    background_tasks.add_task(_refresh)
    return {"status": "refresh queued"}
