"""铺位招商接口：招商清单的整批暂存、逐条核对与一次性入库。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, PageResult
from app.services.leasing import FLOORS, LeasingService

router = APIRouter(prefix="/api/leasing", tags=["铺位招商"])

service = LeasingService()

LIST_FIELDS = ["铺位编号", "楼层", "铺位类型", "面积", "租金", "租期", "签约状态"]
STATUSES = ["待签约", "已签约"]


class StageRow(BaseModel):
    """清单里的一行：行号必须随内容带上来，重复与退回都要按行号说话。"""

    line_no: int = Field(gt=0)
    code: str | None = None
    floor: str | None = None
    booth_type: str | None = None
    area: str | None = None
    rent: Any = None
    term: str | None = None


class StagePayload(BaseModel):
    """第一步：勾选楼层 + 整份清单原文，只做格式与编号检查。"""

    floors: list[str] = Field(default_factory=list)
    rows: list[StageRow] = Field(default_factory=list)


class ConfirmPayload(BaseModel):
    line_no: int
    confirmed: bool = True


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按铺位编号检索"),
    floor: str | None = Query(default=None, description="按楼层筛选"),
    status: str | None = Query(default=None, description="待签约、已签约"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """铺位明细：按编号、楼层与签约状态过滤；没有数据时返回空页。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, floor=floor, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/floors")
def floor_summary() -> dict[str, Any]:
    """楼层汇总：铺位条数从明细当场重算，入库完成后随之刷新。"""
    return {"items": service.floor_summary()}


@router.get("/stage")
def get_stage() -> dict[str, Any]:
    """读取待核对区：整批要么还在（含已退回行与确认状态），要么为空。"""
    batch = service.get_batch()
    return {"batch": batch}


@router.post("/stage")
def stage_batch(payload: StagePayload) -> dict[str, Any]:
    """整批暂存：只做格式与编号检查；重复行按行号标出，租金为空或非数字的整行退回。"""
    batch, message = service.stage_batch(
        floors=payload.floors,
        raw_rows=[row.model_dump() for row in payload.rows],
    )
    if batch is None:
        raise HTTPException(status_code=400, detail=message)
    return {"batch": batch, "message": message}


@router.patch("/stage/confirm", response_model=ActionResult)
def confirm_row(payload: ConfirmPayload) -> ActionResult:
    """逐条确认：暂存阶段不改任何铺位明细，只记录核对结果。"""
    entry, message = service.confirm_row(payload.line_no, payload.confirmed)
    if entry is None:
        return ActionResult(ok=False, message=message)
    state = "已确认" if payload.confirmed else "已取消确认"
    return ActionResult(ok=True, message=f"第 {payload.line_no} 行{state}", entry=entry)


@router.delete("/stage", response_model=ActionResult)
def clear_stage() -> ActionResult:
    """整批清空：不允许只删一部分。"""
    existed = service.clear_batch()
    return ActionResult(ok=True, message="待核对区已整批清空" if existed else "待核对区本来就是空的")


@router.post("/commit")
def commit_batch() -> dict[str, Any]:
    """入库：已有的按编号更新租金与租期，没有的补成待签约；重复提交同一批只认第一次。"""
    result, message, duplicated = service.commit_batch()
    if result is None:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "duplicated": duplicated, "message": message, "result": result}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出铺位招商清单：返回当前铺位明细的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "leasing", "total": total, "items": items}
