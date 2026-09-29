"""招商交接业务规则：两步式暂存、格式与编号校验、逐条确认入库。

整条链路分两步：
1. 暂存：多选楼层后整批拉进待核对区，只做格式（租金必须是数字）与编号（铺位编号
   不能为空、同一份清单的重复行按行号标出）检查，不碰库存。
2. 入库：逐条确认后才写库存，已有的按编号更新租金与租期，没有的补成待签约；
   一次提交里重复确认同一份清单只认第一次。

暂存批次是原子的：要么整批都在，要么整批清空，不留半批。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "leasing"  # 铺位库存
LIST_MODULE = "leasing_list"  # 招商清单来源
STAGING_MODULE = "leasing_staging"  # 暂存批次

SHOP_STATUSES = ["待签约", "已签约", "已退租"]
BATCH_STATUSES = ["待核对", "已入库", "已清空"]


def _parse_rent(value: Any) -> tuple[float | None, bool]:
    """解析租金：只有数字才算有效，空值或不是数字一律整行退回。"""
    if value is None:
        return None, False
    if isinstance(value, bool):
        return None, False
    if isinstance(value, (int, float)):
        return float(value), True
    text = str(value).strip()
    if not text:
        return None, False
    # 去掉千分位逗号、中文逗号与货币单位后再试
    cleaned = text.replace(",", "").replace("，", "").replace("元", "").strip()
    try:
        return float(cleaned), True
    except ValueError:
        return None, False


class LeasingService:
    # ---- 铺位明细 ----
    def list_shops(
        self,
        *,
        keyword: str | None = None,
        floor: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("铺位编号", ""))]
        if floor:
            rows = [row for row in rows if row.get("楼层") == floor]
        if status:
            rows = [row for row in rows if row.get("签约状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_floors(self) -> list[dict[str, Any]]:
        """楼层汇总：铺位条数跟着明细一起算，入库后自动重算。"""
        rows = store.rows(MODULE)
        counts: dict[str, int] = {}
        for row in rows:
            floor = str(row.get("楼层") or "未分层")
            counts[floor] = counts.get(floor, 0) + 1
        return [{"楼层": floor, "铺位条数": counts[floor]} for floor in sorted(counts)]

    def list_floor_options(self) -> list[str]:
        """所有出现过的楼层，供多选楼层时勾选。"""
        floors: set[str] = set()
        for row in store.rows(LIST_MODULE):
            if row.get("楼层"):
                floors.add(str(row["楼层"]))
        for row in store.rows(MODULE):
            if row.get("楼层"):
                floors.add(str(row["楼层"]))
        return sorted(floors)

    # ---- 暂存 ----
    def list_batches(self) -> list[dict[str, Any]]:
        return store.rows(STAGING_MODULE)

    def get_batch(self, batch_id: int) -> dict[str, Any] | None:
        return store.find(STAGING_MODULE, batch_id)

    def stage(self, floors: list[str]) -> tuple[dict[str, Any] | None, str]:
        """整批暂存：把选中楼层的招商清单整批拉进暂存区，只做格式与编号检查。"""
        if not floors:
            return None, "请先勾选要交接的楼层"
        source = store.rows(LIST_MODULE)
        selected = [row for row in source if str(row.get("楼层", "")) in floors]
        if not selected:
            return None, "所选楼层没有可交接的招商清单"

        rows: list[dict[str, Any]] = []
        for idx, src in enumerate(selected, start=1):
            shop_no = str(src.get("铺位编号") or "").strip()
            rent_raw = src.get("租金")
            rent, rent_ok = _parse_rent(rent_raw)
            no_ok = bool(shop_no)
            valid = rent_ok and no_ok
            reasons: list[str] = []
            if not rent_ok:
                reasons.append("租金为空或不是数字")
            if not no_ok:
                reasons.append("铺位编号为空")
            rows.append({
                "id": idx,  # 批次内局部行号，前端按这个引用
                "行号": idx,
                "铺位编号": shop_no,
                "楼层": str(src.get("楼层") or ""),
                "租金_raw": rent_raw,
                "租金": rent,
                "租期": str(src.get("租期") or ""),
                "租金有效": rent_ok,
                "编号有效": no_ok,
                "有效": valid,
                "重复": False,
                "重复行号": [],
                "核对状态": "待核对" if valid else "已退回",
                "退回原因": "、".join(reasons) if reasons else "",
            })

        # 重复行按行号标出：同一份清单里相同铺位编号出现多次
        by_no: dict[str, list[int]] = {}
        for row in rows:
            if row["铺位编号"]:
                by_no.setdefault(row["铺位编号"], []).append(row["行号"])
        for row in rows:
            dup_rows = by_no.get(row["铺位编号"], [])
            if len(dup_rows) > 1:
                row["重复"] = True
                row["重复行号"] = [n for n in dup_rows if n != row["行号"]]

        # 整批入库：要么整批都在，要么整批清空，不做半批
        batches = store.rows(STAGING_MODULE)
        batch_id = max((int(b.get("id", 0)) for b in batches), default=0) + 1
        batch_no = f"STG-{datetime.now():%Y%m%d%H%M%S}-{batch_id:03d}"
        batch = {
            "id": batch_id,
            "批次号": batch_no,
            "楼层": list(floors),
            "状态": "待核对",
            "创建时间": datetime.now().isoformat(timespec="seconds"),
            "rows": rows,
        }
        batches.append(batch)
        return batch, f"已整批暂存 {len(rows)} 行，其中退回 {sum(1 for r in rows if not r['有效'])} 行"

    # ---- 入库 ----
    def confirm(self, batch_id: int, row_ids: list[int] | None = None) -> tuple[dict[str, Any] | None, str]:
        """逐条确认后入库。

        已有的铺位按编号更新租金与租期，没有的补成待签约；一次提交里重复确认同一份
        清单只认第一次。
        """
        batch = store.find(STAGING_MODULE, batch_id)
        if batch is None:
            return None, "暂存批次不存在或已清空"
        if batch["状态"] == "已清空":
            return None, "该批次已整批清空，不能入库"
        if batch["状态"] == "已入库":
            return None, "该批次已入库，不能重复提交"

        rows = batch["rows"]
        if row_ids is not None:
            id_set = {int(x) for x in row_ids}
            targets = [row for row in rows if row["id"] in id_set]
        else:
            targets = [row for row in rows if row["核对状态"] == "待核对" and row["有效"]]
        if not targets:
            return None, "没有可入库的有效行"

        shops = store.rows(MODULE)
        processed: set[str] = set()  # 本次提交已处理的铺位编号，重复只认第一次
        done = 0
        skipped = 0
        for row in targets:
            if row["核对状态"] != "待核对":
                skipped += 1
                continue
            if not row["有效"]:
                row["核对状态"] = "已退回"
                skipped += 1
                continue
            shop_no = row["铺位编号"]
            if shop_no in processed:
                # 同一份清单重复确认，只认第一次
                row["核对状态"] = "已退回"
                row["退回原因"] = "重复清单，本次只认第一次"
                skipped += 1
                continue
            processed.add(shop_no)
            # 入库：已有按编号更新租金与租期，没有的补成待签约
            existing = next((s for s in shops if s.get("铺位编号") == shop_no), None)
            if existing is not None:
                existing["租金"] = row["租金"]
                existing["租期"] = row["租期"]
            else:
                new_id = max((int(s.get("id", 0)) for s in shops), default=0) + 1
                shops.append({
                    "id": new_id,
                    "铺位编号": shop_no,
                    "楼层": row["楼层"],
                    "租金": row["租金"],
                    "租期": row["租期"],
                    "签约状态": "待签约",
                    "pending": True,
                    "abnormal": False,
                })
            row["核对状态"] = "已确认"
            done += 1

        # 本批待核对的有效行都处理完了，批次置为已入库
        remaining = [r for r in rows if r["核对状态"] == "待核对" and r["有效"]]
        if not remaining:
            batch["状态"] = "已入库"
        return batch, f"已入库 {done} 条，跳过 {skipped} 条"

    def discard(self, batch_id: int) -> tuple[dict[str, Any] | None, str]:
        """整批清空：把整个暂存批次标记为已清空，不留半批。"""
        batch = store.find(STAGING_MODULE, batch_id)
        if batch is None:
            return None, "暂存批次不存在或已清空"
        if batch["状态"] == "已入库":
            return None, "该批次已入库，不能清空"
        if batch["状态"] == "已清空":
            return batch, "该批次已清空，无需重复操作"
        batch["状态"] = "已清空"
        return batch, "已整批清空"
