"""铺位招商业务规则：招商清单的两步式交接。

第一步只做格式与编号检查，整批暂存进待核对区（同批原子替换，不留半批）；
第二步逐条确认后入库：已有铺位按编号更新租金与租期，没有的补成待签约。
楼层汇总不落地，始终从铺位明细表重算派生。
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "leasing"
FLOORS = ["1F", "2F", "3F", "B1"]
SIGNED = "已签约"
PENDING_SIGN = "待签约"

# 租金只接受非负数字：整数或小数；空串、文字、带负号/千分位的都按「不是数字」退回。
NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")

REQUIRED_COLUMNS = ["铺位编号", "楼层", "铺位类型", "面积", "租金", "租期"]


class LeasingService:
    def __init__(self) -> None:
        # 待核对区全局只挂一份清单：新批暂存时整体替换，从根上杜绝「半批」状态。
        self._lock = threading.RLock()
        self._batch: dict[str, Any] | None = None

    # ---------- 铺位明细 ----------

    def list_entries(
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

    def floor_summary(self) -> list[dict[str, Any]]:
        """楼层汇总：铺位条数始终从明细表当场重算，不另存一份。"""
        rows = store.rows(MODULE)
        summary: list[dict[str, Any]] = []
        for name in FLOORS:
            floor_rows = [row for row in rows if row.get("楼层") == name]
            summary.append({
                "楼层": name,
                "铺位条数": len(floor_rows),
                "已签约": sum(1 for row in floor_rows if row.get("签约状态") == SIGNED),
                "待签约": sum(1 for row in floor_rows if row.get("签约状态") == PENDING_SIGN),
            })
        return summary

    # ---------- 第一步：整批暂存（只做格式与编号检查） ----------

    def get_batch(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._batch is None else dict(self._batch)

    def stage_batch(
        self, floors: list[str], raw_rows: list[dict[str, Any]]
    ) -> tuple[dict[str, Any] | None, str]:
        floors = [str(item or "").strip() for item in floors]
        invalid_floors = [name for name in floors if name not in FLOORS]
        if invalid_floors:
            return None, f"楼层不存在：{'、'.join(invalid_floors)}"
        if not floors:
            return None, "请至少勾选一个楼层"
        if not raw_rows:
            return None, "清单里没有可暂存的行"

        seen: dict[str, list[int]] = {}
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for raw in raw_rows:
            line_no = int(raw.get("line_no") or 0)
            code = str(raw.get("code") or "").strip()
            floor = str(raw.get("floor") or "").strip()
            rent_text = str(raw.get("rent") if raw.get("rent") is not None else "").strip()

            reason = self._check_row(code=code, floor=floor, floors=floors, rent_text=rent_text)
            if reason is not None:
                rejected.append({
                    "line_no": line_no,
                    "code": code or None,
                    "floor": floor or None,
                    "rent": rent_text or None,
                    "reason": reason,
                })
                continue

            rent = float(rent_text)
            if rent.is_integer():
                rent = int(rent)
            entry = {
                "line_no": line_no,
                "铺位编号": code,
                "楼层": floor,
                "铺位类型": str(raw.get("booth_type") or "").strip() or None,
                "面积": str(raw.get("area") or "").strip() or None,
                "租金": rent,
                "租期": str(raw.get("term") or "").strip() or None,
                "confirmed": False,
                "duplicate_lines": [],
            }
            accepted.append(entry)
            seen.setdefault(code, []).append(line_no)

        # 同一编号出现多次：把同清单的重复行号互相标出来，核对时一眼能看到。
        for entry in accepted:
            lines = seen.get(entry["铺位编号"], [])
            if len(lines) > 1:
                entry["duplicate_lines"] = [no for no in lines if no != entry["line_no"]]

        # 先把整批在内存里组装完整，再一次性挂上去：中途任何一步失败都不会留下半批。
        new_batch = {
            "id": uuid.uuid4().hex[:12],
            "floors": floors,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "accepted": accepted,
            "rejected": rejected,
            "committed": False,
            "result": None,
        }
        with self._lock:
            self._batch = new_batch
        return dict(new_batch), ""

    @staticmethod
    def _check_row(*, code: str, floor: str, floors: list[str], rent_text: str) -> str | None:
        if not code:
            return "铺位编号为空"
        if not floor:
            return "楼层为空"
        if floor not in FLOORS:
            return f"楼层「{floor}」不在可选范围内"
        if floor not in floors:
            return f"楼层「{floor}」不在本次勾选范围内"
        if not re.fullmatch(rf"{re.escape(floor)}-\d{{3}}", code):
            return f"铺位编号「{code}」与楼层「{floor}」不匹配，应为 {floor}-三位序号"
        if not rent_text:
            return "租金为空，整行退回"
        if not NUMBER_RE.fullmatch(rent_text):
            return f"租金「{rent_text}」不是数字，整行退回"
        return None

    # ---------- 第二步：逐条确认 ----------

    def confirm_row(self, line_no: int, confirmed: bool) -> tuple[dict[str, Any] | None, str]:
        with self._lock:
            if self._batch is None:
                return None, "待核对区没有清单"
            if self._batch["committed"]:
                return None, "这份清单已入库，不能再核对"
            for entry in self._batch["accepted"]:
                if entry["line_no"] == line_no:
                    entry["confirmed"] = confirmed
                    return dict(entry), ""
            return None, f"第 {line_no} 行不在待核对清单中"

    def clear_batch(self) -> bool:
        """整批清空：待核对区要么留整批，要么直接没有。"""
        with self._lock:
            existed = self._batch is not None
            self._batch = None
            return existed

    # ---------- 入库：编号更新 / 缺号补待签约，同批提交幂等 ----------

    def commit_batch(self) -> tuple[dict[str, Any] | None, str, bool]:
        """返回 (结果, 错误说明, 是否重复提交)。重复确认同一份清单只认第一次。"""
        with self._lock:
            batch = self._batch
            if batch is None:
                return None, "待核对区没有清单，无法入库", False
            if batch["committed"]:
                return dict(batch["result"]), "这份清单已经入库过，本次提交未重复执行", True

            accepted: list[dict[str, Any]] = batch["accepted"]
            unconfirmed = [entry["line_no"] for entry in accepted if not entry["confirmed"]]
            if unconfirmed:
                return None, f"还有 {len(unconfirmed)} 行未逐条确认（行号：{_join_lines(unconfirmed)}）", False
            if not accepted:
                return None, "清单里没有可入库的行", False

            rows = store.rows(MODULE)
            existing = {str(row.get("铺位编号")): row for row in rows}
            next_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1

            updated: list[int] = []
            inserted: list[int] = []
            skipped: list[dict[str, Any]] = []
            applied_codes: set[str] = set()
            for entry in accepted:
                code = entry["铺位编号"]
                if code in applied_codes:
                    skipped.append({
                        "line_no": entry["line_no"],
                        "code": code,
                        "reason": "同一编号重复行，只认第一次确认",
                    })
                    continue
                applied_codes.add(code)

                target = existing.get(code)
                if target is not None:
                    target["租金"] = entry["租金"]
                    target["租期"] = entry["租期"]
                    updated.append(entry["line_no"])
                else:
                    booth = {
                        "id": next_id,
                        "status": PENDING_SIGN,
                        "pending": True,
                        "abnormal": False,
                        "签约状态": PENDING_SIGN,
                        "铺位编号": code,
                        "楼层": entry["楼层"],
                        "铺位类型": entry["铺位类型"],
                        "面积": entry["面积"],
                        "租金": entry["租金"],
                        "租期": entry["租期"],
                    }
                    rows.append(booth)
                    existing[code] = booth
                    next_id += 1
                    inserted.append(entry["line_no"])

            # 明细落库后当场重算楼层汇总，条数与明细保持一致。
            result = {
                "batch_id": batch["id"],
                "updated": len(updated),
                "updated_lines": updated,
                "inserted": len(inserted),
                "inserted_lines": inserted,
                "skipped": skipped,
                "rejected_count": len(batch["rejected"]),
                "floors": self.floor_summary(),
                "committed_at": datetime.now().isoformat(timespec="seconds"),
            }
            batch["committed"] = True
            batch["result"] = result
            return dict(result), "", False


def _join_lines(lines: list[int]) -> str:
    return "、".join(str(line) for line in lines)
