"""招商交接接口：铺位明细、楼层汇总、两步式暂存与入库。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, LeasingConfirmPayload, LeasingStagePayload, PageResult
from app.services.leasing import LeasingService

router = APIRouter(prefix="/api/leasing", tags=["招商交接"])

service = LeasingService()

SHOP_STATUSES = ["待签约", "已签约", "已退租"]


@router.get("", response_model=PageResult[dict])
def list_shops(
    keyword: str | None = Query(default=None, description="按铺位编号检索"),
    floor: str | None = Query(default=None, description="按楼层过滤"),
    status: str | None = Query(default=None, description="待签约、已签约、已退租"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """铺位明细列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_shops(keyword=keyword, floor=floor, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/floors")
def list_floors() -> dict[str, Any]:
    """楼层汇总：铺位条数跟着明细一起重算，同时返回可勾选的楼层选项。"""
    return {"items": service.list_floors(), "options": service.list_floor_options()}


@router.get("/staging")
def list_batches() -> dict[str, Any]:
    """暂存区：返回所有整批暂存的批次，每批都是完整的一行一行。"""
    return {"items": service.list_batches()}


@router.post("/staging", response_model=ActionResult)
def stage(payload: LeasingStagePayload) -> ActionResult:
    """多选楼层后整批暂存进待核对区，只做格式与编号检查。"""
    batch, message = service.stage(payload.floors)
    if batch is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=batch)


@router.get("/staging/{batch_id}")
def get_batch(batch_id: int) -> dict[str, Any]:
    """读取单个暂存批次；不存在或已清空时给出可读的错误说明。"""
    batch = service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="暂存批次不存在或已清空")
    return batch


@router.post("/staging/{batch_id}/confirm", response_model=ActionResult)
def confirm(batch_id: int, payload: LeasingConfirmPayload) -> ActionResult:
    """逐条确认后入库：已有铺位按编号更新租金与租期，没有的补成待签约。"""
    batch, message = service.confirm(batch_id, payload.row_ids)
    if batch is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=batch)


@router.post("/staging/{batch_id}/discard", response_model=ActionResult)
def discard(batch_id: int) -> ActionResult:
    """整批清空：把整个暂存批次标记为已清空，不留半批。"""
    batch, message = service.discard(batch_id)
    if batch is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=batch)


@router.get("/export")
def export_shops() -> dict[str, Any]:
    """导出铺位清单：返回全量数据。"""
    items, total = service.list_shops(page=1, size=10000)
    return {"module": "leasing", "total": total, "items": items}
