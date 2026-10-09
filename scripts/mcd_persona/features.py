"""把精简后的数据整理成可计算的统计指标。所有结论都来自这里，便于追溯。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .catalog import (CATEGORIES, FOOD_CATEGORIES, NutritionIndex, categorize, is_coffee, is_zero_sugar,
                      normalize_name, parse_nutrition)

SOLAR_TERMS = (
    "立春", "雨水", "惊蛰", "春分", "清明", "谷雨", "立夏", "小满", "芒种", "夏至", "小暑", "大暑",
    "立秋", "处暑", "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至", "小寒", "大寒",
)
PERIODS = ("早餐", "午餐", "下午茶", "晚餐", "夜宵")
WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
SCENES = ("堂食", "外带", "外送", "得来速", "团餐")
BREAKFAST_END = (10, 30)  # 麦当劳早餐时段截止 10:30


@dataclass
class Item:
    code: str
    name: str
    qty: int
    category: str

    @property
    def key(self) -> str:
        return self.code or normalize_name(self.name)


@dataclass
class Order:
    id: str
    time: datetime
    order_type: str
    be_type: str
    store: str
    items: List[Item]
    take_way: Optional[str] = None
    coupon_count: Optional[int] = None
    discount_ratio: Optional[float] = None

    @property
    def delivery(self) -> bool:
        return self.order_type == "2"

    @property
    def period(self) -> str:
        hm = (self.time.hour, self.time.minute)
        if 4 <= self.time.hour and hm < BREAKFAST_END:
            return "早餐"
        if self.time.hour >= 21 or self.time.hour < 4:
            return "夜宵"
        if self.time.hour < 14:
            return "午餐"
        if self.time.hour < 17:
            return "下午茶"
        return "晚餐"

    @property
    def scene(self) -> str:
        if self.be_type == "6":
            return "团餐"
        if self.be_type == "5":
            return "得来速"
        if self.delivery:
            return "外送"
        if self.take_way in ("堂食", "外带"):
            return self.take_way
        return "外带"  # 到店但没有详情时，按最常见的外带处理

    @property
    def main_qty(self) -> int:
        return sum(it.qty for it in self.items if it.category == "主食")


@dataclass
class Features:
    order_count: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    span_days: Optional[int] = None
    per_month: Optional[float] = None
    confidence: str = "待解锁"
    # 四个维度（0-100，None 表示数据不足）
    breakfast_score: Optional[int] = None
    delivery_score: Optional[int] = None
    loyalty_score: Optional[int] = None
    thrift_score: Optional[int] = None
    # 时间
    period_counts: Dict[str, int] = field(default_factory=dict)
    weekday_counts: Dict[str, int] = field(default_factory=dict)
    weekend_share: Optional[int] = None
    top_periods: List[str] = field(default_factory=list)   # 次数最多的时段，可能并列
    top_weekdays: List[str] = field(default_factory=list)
    workday_breakfast: int = 0
    # 场景与份量
    scene_counts: Dict[str, int] = field(default_factory=dict)
    solo_orders: int = 0
    share_orders: int = 0
    # 省钱
    detail_count: int = 0
    coupon_orders: int = 0
    coupon_rate: Optional[int] = None
    avg_discount: Optional[int] = None  # 用券订单的平均优惠比例
    # 口味
    favorite_food: Optional[Tuple[str, str, int]] = None  # (code, name, 出现订单数)
    favorite_drink: Optional[Tuple[str, str, int]] = None
    top_foods: List[Tuple[str, str]] = field(default_factory=list)
    category_shares: Dict[str, int] = field(default_factory=dict)
    distinct_food_count: int = 0
    dessert_orders: int = 0
    coffee_orders: int = 0
    drink_count: int = 0
    zero_sugar_drinks: int = 0
    store_count: int = 0
    # 营养
    avg_kcal: Optional[int] = None
    avg_protein: Optional[int] = None
    kcal_coverage: Optional[int] = None
    # 积分、奖品、券包
    points: Dict[str, float] = field(default_factory=dict)
    points_ratio: Optional[int] = None
    solar_terms: List[str] = field(default_factory=list)
    other_prizes: int = 0
    mall_count: Optional[int] = None
    coupon_wallet: Optional[int] = None
    coupons_expiring_today: int = 0
    notes: List[str] = field(default_factory=list)


def _pct(x: float) -> int:
    return int(round(x * 100))


def _parse_time(s: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_orders(order_data: Any, details: Optional[List[Dict[str, Any]]] = None) -> List[Order]:
    rows = order_data.get("list", []) if isinstance(order_data, dict) else (order_data or [])
    by_id = {str(d.get("orderId")): d for d in (details or [])}
    orders = []
    for row in rows:
        status = str(row.get("orderStatus", ""))
        if "取消" in status or "退款" in status:
            continue
        t = _parse_time(row.get("createTime"))
        if not t:
            continue
        items: List[Item] = []
        for p in row.get("orderProductList") or []:
            qty = int(p.get("quantity") or 1)
            combo = p.get("comboItemList") or []
            if combo:
                for c in combo:
                    name = str(c.get("name") or c.get("productName") or "").strip()
                    items.append(Item(str(c.get("productCode") or ""), name,
                                      qty * int(c.get("quantity") or 1), categorize(name)))
            else:
                name = str(p.get("productName") or "").strip()
                items.append(Item(str(p.get("productCode") or ""), name, qty, categorize(name)))
        oid = str(row.get("orderId") or "")
        d = by_id.get(oid, {})
        orders.append(Order(
            id=oid, time=t,
            order_type=str(row.get("orderType") or ""),
            be_type=str(row.get("beType") or ""),
            store=str(row.get("storeCode") or ""),
            items=items,
            take_way=d.get("takeWay"),
            coupon_count=d.get("couponCount") if d else None,
            discount_ratio=d.get("discountRatio") if d else None,
        ))
    orders.sort(key=lambda o: o.time)
    return orders


def compute(bundle: Dict[str, Any]) -> Features:
    f = Features()
    orders = parse_orders(bundle.get("order-list") or {}, bundle.get("query-order"))
    f.order_count = n = len(orders)
    f.confidence = "高" if n >= 6 else "中" if n >= 3 else "低" if n >= 1 else "待解锁"

    if orders:
        now = _parse_time((bundle.get("now-time-info") or {}).get("formatted")) or orders[-1].time
        f.first_date = orders[0].time.strftime("%Y-%m-%d")
        f.last_date = orders[-1].time.strftime("%Y-%m-%d")
        f.span_days = max((now - orders[0].time).days, 1)
        f.per_month = round(n / f.span_days * 30, 1)
        f.breakfast_score = _pct(sum(o.period == "早餐" for o in orders) / n)
        f.delivery_score = _pct(sum(o.delivery for o in orders) / n)
        f.store_count = len({o.store for o in orders if o.store})
        _time_stats(f, orders)
        _scene_stats(f, orders)
        _coupon_stats(f, orders)
        _food_stats(f, orders)
        _nutrition_stats(f, orders, bundle.get("list-nutrition-foods"))
        if n < 3:
            f.notes.append(f"只有 {n} 单历史订单，人格是初步判定，多点几单会更准")
    else:
        f.notes.append("还没有读取到历史订单，点几单之后就能解锁完整的麦门人格")

    _points_stats(f, bundle.get("query-my-account"))
    _prize_stats(f, bundle.get("query-my-prizes"))
    _wallet_stats(f, bundle.get("query-my-coupons"), bundle.get("mall-order-list"))
    _thrift_score(f)
    return f


def _time_stats(f: Features, orders: List[Order]) -> None:
    periods = Counter(o.period for o in orders)
    weekdays = Counter(WEEKDAYS[o.time.weekday()] for o in orders)
    f.period_counts = {p: periods[p] for p in PERIODS if periods[p]}
    f.weekday_counts = {d: weekdays[d] for d in WEEKDAYS if weekdays[d]}
    f.weekend_share = _pct(sum(o.time.weekday() >= 5 for o in orders) / len(orders))
    f.top_periods = [p for p in PERIODS if periods[p] == max(periods.values())]
    f.top_weekdays = [d for d in WEEKDAYS if weekdays[d] == max(weekdays.values())]
    f.workday_breakfast = sum(o.period == "早餐" and o.time.weekday() < 5 for o in orders)


def favorite_slot(f: Features) -> str:
    """“最常出没”的文案，如实处理并列的情况。"""
    days = f.top_weekdays
    day = days[0] if len(days) == 1 else "和".join(days) if len(days) == 2 else "不挑日子"
    periods = f.top_periods
    period = (f"{periods[0]}时段" if len(periods) == 1 else
              f"{'和'.join(periods)}时段" if len(periods) == 2 else "全天候")
    return f"{day} · {period}"


def _scene_stats(f: Features, orders: List[Order]) -> None:
    scenes = Counter(o.scene for o in orders)
    f.scene_counts = {s: scenes[s] for s in SCENES if scenes[s]}
    f.solo_orders = sum(o.main_qty <= 1 for o in orders)
    f.share_orders = sum(o.main_qty >= 3 for o in orders)


def _coupon_stats(f: Features, orders: List[Order]) -> None:
    detailed = [o for o in orders if o.coupon_count is not None]
    f.detail_count = len(detailed)
    if not detailed:
        return
    with_coupon = [o for o in detailed if o.coupon_count]
    f.coupon_orders = len(with_coupon)
    f.coupon_rate = _pct(len(with_coupon) / len(detailed))
    ratios = [o.discount_ratio for o in with_coupon if o.discount_ratio]
    if ratios:
        f.avg_discount = _pct(sum(ratios) / len(ratios))


def _food_stats(f: Features, orders: List[Order]) -> None:
    names: Dict[str, str] = {}
    food_orders: Counter = Counter()
    drink_orders: Counter = Counter()
    cat_qty: Counter = Counter()
    per_order_foods: List[set] = []

    for o in orders:
        foods, drinks = set(), set()
        has_dessert = has_coffee = False
        for it in o.items:
            names.setdefault(it.key, it.name)
            cat_qty[it.category] += it.qty
            if it.category in FOOD_CATEGORIES:
                foods.add(it.key)
            if it.category == "甜品":
                has_dessert = True
            if it.category == "饮品":
                drinks.add(it.key)
                f.drink_count += it.qty
                if is_zero_sugar(it.name):
                    f.zero_sugar_drinks += it.qty
                if is_coffee(it.name):
                    has_coffee = True
        food_orders.update(foods)
        drink_orders.update(drinks)
        per_order_foods.append(foods)
        f.dessert_orders += has_dessert
        f.coffee_orders += has_coffee

    total_qty = sum(cat_qty.values())
    if total_qty:
        f.category_shares = {c: _pct(cat_qty.get(c, 0) / total_qty) for c in CATEGORIES if cat_qty.get(c)}
    f.distinct_food_count = len(food_orders)

    # 专一度：有多少单包含“在别的订单里也出现过”的单品
    if len(orders) >= 2:
        repeated = {k for k, c in food_orders.items() if c >= 2}
        f.loyalty_score = _pct(sum(1 for s in per_order_foods if s & repeated) / len(orders))

    def rank(counter: Counter, prefer_main: bool) -> List[Tuple[str, str, int]]:
        def sort_key(kv):
            key, count = kv
            is_main = categorize(names[key]) == "主食"
            return (-count, 0 if (prefer_main and is_main) else 1, names[key])
        return [(k, names[k], c) for k, c in sorted(counter.items(), key=sort_key)]

    foods_ranked = rank(food_orders, prefer_main=True)
    if foods_ranked:
        f.favorite_food = foods_ranked[0]
        f.top_foods = [(code, name) for code, name, _ in foods_ranked[:3]]
    drinks_ranked = rank(drink_orders, prefer_main=False)
    if drinks_ranked:
        f.favorite_drink = drinks_ranked[0]


def _nutrition_stats(f: Features, orders: List[Order], nutrition_data: Any) -> None:
    index = NutritionIndex(parse_nutrition(nutrition_data)) if nutrition_data else None
    if not index or not len(index):
        return
    total_qty = matched_qty = 0
    kcal = protein = 0.0
    for o in orders:
        for it in o.items:
            total_qty += it.qty
            n = index.lookup(it.name)
            if n:
                matched_qty += it.qty
                kcal += n.kcal * it.qty
                protein += n.protein * it.qty
    if not total_qty:
        return
    f.kcal_coverage = _pct(matched_qty / total_qty)
    # 覆盖率太低时不展示营养数据，避免误导
    if f.kcal_coverage >= 60:
        f.avg_kcal = int(round(kcal / len(orders)))
        f.avg_protein = int(round(protein / len(orders)))


def _points_stats(f: Features, account: Any) -> None:
    if not isinstance(account, dict):
        return
    keys = {
        "available": "availablePoint",
        "accumulative": "accumulativePoint",
        "used": "usedPoint",
        "expired": "expiredPoint",
        "expiring_this_month": "currentMouthExpirePoint",
        "expiring_next_month": "nextMouthExpirePoint",
    }
    for k, src in keys.items():
        try:
            f.points[k] = float(account.get(src))
        except (TypeError, ValueError):
            pass
    used, expired = f.points.get("used", 0), f.points.get("expired", 0)
    if used + expired > 0:
        f.points_ratio = _pct(used / (used + expired))


def _prize_stats(f: Features, prizes_data: Any) -> None:
    prizes = prizes_data.get("prizes", []) if isinstance(prizes_data, dict) else []
    names = [str(p.get("name", "")) for p in prizes]
    f.solar_terms = [t for t in SOLAR_TERMS if t in set(names)]
    f.other_prizes = sum(1 for nm in names if nm not in SOLAR_TERMS)


def _wallet_stats(f: Features, coupons: Any, mall: Any) -> None:
    if isinstance(coupons, dict) and "coupons" in coupons:
        f.coupon_wallet = len(coupons["coupons"])
        f.coupons_expiring_today = sum(1 for c in coupons["coupons"] if c.get("expiringToday"))
    if isinstance(mall, dict) and "count" in mall:
        f.mall_count = int(mall["count"])


def _thrift_score(f: Features) -> None:
    """精打细算：用券比例（行为数据，权重 60%）+ 积分利用率（40%），有哪个用哪个。"""
    parts = []
    if f.coupon_rate is not None and f.detail_count >= max(1, f.order_count // 2):
        parts.append((f.coupon_rate, 0.6))
    if f.points_ratio is not None:
        parts.append((f.points_ratio, 0.4))
    if parts:
        f.thrift_score = int(round(sum(s * w for s, w in parts) / sum(w for _, w in parts)))
