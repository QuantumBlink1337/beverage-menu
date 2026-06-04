from fastapi import APIRouter, Query

from controllers.beverages import get_beverages
from models import BeveragesResponse

router = APIRouter()


@router.get("/beverages", response_model=BeveragesResponse)
async def beverages(host: bool = Query(False)):
    return await get_beverages(host_mode=host)
