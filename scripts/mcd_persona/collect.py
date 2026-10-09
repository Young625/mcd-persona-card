"""从麦当劳 MCP 拉取数据，或从本地文件加载，统一成精简后的 bundle。

bundle 结构（采集后立即精简，只保留计算需要的字段）：
    {
      "order-list":           {"list": [...]},          # 去掉门店名称和金额
      "query-order":          [{orderId, takeWay, couponCount, discountRatio}],
      "query-my-account":     {...积分账户...},
      "query-my-prizes":      {"prizes": [{name, prizeTypeText}]},
      "query-my-coupons":     {"coupons": [{expiringToday}], "totalCount": n},
      "mall-order-list":      {"count": n},
      "list-nutrition-foods": "<紧凑表格文本>",
      "now-time-info":        {"formatted": "..."},
      "_meta": {"source": "live|cache|demo|input", "fetchedAt": "..."}
    }

本项目只调用只读 Tool，绝不调用下单、领券、抽奖等会改变账户状态的 Tool。
订单详情里的门店地址、取餐码、支付单号、备注、金额等字段在采集时就被丢弃，不会写入缓存。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .mcp_client import MCPClient, MCPError
from .paths import CACHE_FILE, DEMO_FILE

READ_ONLY_TOOLS = (
    "now-time-info",
    "order-list",
    "query-order",
    "query-my-account",
    "query-my-prizes",
    "query-my-coupons",
    "mall-order-list",
    "list-nutrition-foods",
)

MAX_PRIZE_PAGES = 3
MAX_MALL_PAGES = 5

Log = Callable[[str], None]


def unwrap(payload: Any) -> Any:
    """接受完整的 tools/call 结果、structuredContent 或 data 本身，返回 data 部分。"""
    if isinstance(payload, dict):
        if "structuredContent" in payload and payload["structuredContent"] is not None:
            payload = payload["structuredContent"]
        if "success" in payload and "data" in payload:
            if payload.get("success") is False:
                raise MCPError(f"接口返回失败：{payload.get('message')}")
            return payload["data"]
    return payload


# ---------------- 精简：只保留需要的字段 ----------------

def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def slim_orders(data: Any) -> Dict[str, Any]:
    rows = data.get("list", []) if isinstance(data, dict) else (data or [])
    keep = ("orderId", "orderType", "beType", "createTime", "storeCode", "orderStatus", "orderProductList")
    return {"list": [{k: r.get(k) for k in keep} for r in rows if isinstance(r, dict)]}


def slim_order_detail(data: Any) -> Optional[Dict[str, Any]]:
    data = unwrap(data)
    if not isinstance(data, dict) or "orderId" not in data:
        return None
    if "couponCount" in data or "discountRatio" in data:  # 已经精简过
        return {k: data.get(k) for k in ("orderId", "takeWay", "couponCount", "discountRatio")}
    total = _to_float(data.get("totalAmount"))
    discount = _to_float(data.get("totalDiscountAmount"))
    ratio = round(discount / total, 3) if total and discount is not None and total > 0 else None
    return {
        "orderId": str(data["orderId"]),
        "takeWay": data.get("takeWay") or None,
        "couponCount": len(data.get("couponList") or []),
        "discountRatio": ratio,
    }


def slim_order_details(data: Any) -> List[Dict[str, Any]]:
    items = data.values() if isinstance(data, dict) else (data or [])
    return [d for d in (slim_order_detail(x) for x in items) if d]


def slim_prizes(data: Any) -> Dict[str, Any]:
    prizes = data.get("prizes", []) if isinstance(data, dict) else (data or [])
    return {"prizes": [{"name": p.get("name"), "prizeTypeText": p.get("prizeTypeText")}
                       for p in prizes if isinstance(p, dict)]}


def slim_coupons(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict) and "coupons" in data and all("expiringToday" in c for c in data["coupons"]):
        return data
    coupons = data.get("coupons", []) if isinstance(data, dict) else (data or [])
    out = []
    for c in coupons:
        labels = {t.get("label") for t in (c.get("tags") or []) if isinstance(t, dict)}
        out.append({"expiringToday": "今日到期" in labels})
    return {"coupons": out, "totalCount": len(out)}


def slim_mall(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict) and "count" in data:
        return {"count": int(data["count"])}
    pages = data if isinstance(data, list) else [data]
    count = sum(len(p.get("list") or []) for p in pages if isinstance(p, dict))
    return {"count": count}


def slim(bundle: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "order-list" in bundle:
        out["order-list"] = slim_orders(bundle["order-list"])
    if "query-order" in bundle:
        out["query-order"] = slim_order_details(bundle["query-order"])
    if "query-my-prizes" in bundle:
        out["query-my-prizes"] = slim_prizes(bundle["query-my-prizes"])
    if "query-my-coupons" in bundle:
        out["query-my-coupons"] = slim_coupons(bundle["query-my-coupons"])
    if "mall-order-list" in bundle:
        out["mall-order-list"] = slim_mall(bundle["mall-order-list"])
    for key in ("query-my-account", "list-nutrition-foods"):
        if key in bundle:
            out[key] = bundle[key]
    if isinstance(bundle.get("now-time-info"), dict):
        out["now-time-info"] = {"formatted": bundle["now-time-info"].get("formatted")}
    out["_meta"] = bundle.get("_meta", {})
    return out


# ---------------- 拉取 ----------------

def _safe(log: Log, name: str, fn: Callable[[], Any], default: Any) -> Any:
    """非核心数据拉取失败时不中断，记一条日志后用默认值。"""
    try:
        return fn()
    except MCPError as e:
        log(f"{name} 获取失败，已跳过：{e}")
        return default


def fetch_live(client: MCPClient, log: Log = lambda _: None) -> Dict[str, Any]:
    raw: Dict[str, Any] = {}
    for name in ("now-time-info", "order-list", "query-my-account", "list-nutrition-foods"):
        log(f"调用 {name} …")
        raw[name] = unwrap(client.call_tool_data(name))

    orders = slim_orders(raw["order-list"])["list"]
    log(f"调用 query-order × {len(orders)} …")
    raw["query-order"] = [
        d for d in (
            _safe(log, "订单详情", lambda oid=o["orderId"]: slim_order_detail(
                client.call_tool_data("query-order", {"orderId": oid})), None)
            for o in orders if o.get("orderId")
        ) if d
    ]

    log("调用 query-my-prizes …")
    def prizes() -> List[Any]:
        items: List[Any] = []
        for page in range(1, MAX_PRIZE_PAGES + 1):
            data = unwrap(client.call_tool_data("query-my-prizes", {"pageNum": str(page), "pageSize": "50"}))
            items.extend(data.get("prizes") or [])
            if not data.get("hasMore"):
                break
        return items
    raw["query-my-prizes"] = {"prizes": _safe(log, "query-my-prizes", prizes, [])}

    log("调用 query-my-coupons …")
    raw["query-my-coupons"] = _safe(log, "query-my-coupons", lambda: unwrap(
        client.call_tool_data("query-my-coupons", {"page": "1", "pageSize": "200"})), {"coupons": []})

    log("调用 mall-order-list …")
    def mall() -> List[Any]:
        pages, last_id = [], None
        for _ in range(MAX_MALL_PAGES):
            args = {"size": 10} if last_id is None else {"size": 10, "lastId": last_id}
            data = unwrap(client.call_tool_data("mall-order-list", args))
            page = data[0] if isinstance(data, list) and data else data
            pages.append(page)
            if not isinstance(page, dict) or not page.get("hasNext"):
                break
            last_id = page.get("lastId")
        return pages
    raw["mall-order-list"] = _safe(log, "mall-order-list", mall, [])

    raw["_meta"] = {"source": "live", "fetchedAt": time.strftime("%Y-%m-%d %H:%M:%S")}
    return slim(raw)


# ---------------- 本地文件 ----------------

def save_cache(bundle: Dict[str, Any], path: Path = CACHE_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load_file(path: Path, source: str) -> Dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    bundle: Dict[str, Any] = {}
    for key, value in raw.items():
        if key == "query-order":
            bundle[key] = value  # 订单详情是多次调用结果的列表，逐个在 slim 里处理
        elif key in READ_ONLY_TOOLS:
            bundle[key] = unwrap(value)
    if "order-list" not in bundle:
        raise MCPError(f"{path} 缺少必需的数据：order-list")
    bundle["_meta"] = {**(raw.get("_meta") or {}), "source": source}
    return slim(bundle)


def load_demo() -> Dict[str, Any]:
    return load_file(DEMO_FILE, "demo")


def get_bundle(
    *,
    demo: bool = False,
    input_path: Optional[str] = None,
    use_cache: bool = False,
    client_factory: Optional[Callable[[], MCPClient]] = None,
    log: Log = lambda _: None,
) -> Dict[str, Any]:
    if demo:
        return load_demo()
    if input_path:
        return load_file(Path(input_path), "input")
    if use_cache and CACHE_FILE.is_file():
        return load_file(CACHE_FILE, "cache")
    if client_factory is None:
        raise MCPError("缺少 MCP 客户端")
    bundle = fetch_live(client_factory(), log)
    save_cache(bundle)
    return bundle
