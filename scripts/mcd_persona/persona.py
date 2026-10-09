"""统计指标 → 麦门人格（四维主人格 + 麦门角色 + 积分段位）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .features import SOLAR_TERMS, Features
from .paths import PERSONA_FILE

MAX_ROLES = 3


@dataclass
class AxisResult:
    id: str
    left: str
    right: str
    score: Optional[int]  # 偏向左侧的程度 0-100，None 表示数据不足
    char: str
    leaning: str  # 落在哪一侧的名称
    evidence: str


@dataclass
class Role:
    name: str
    evidence: str


@dataclass
class Tier:
    name: str
    points: int
    next_name: Optional[str] = None
    gap: Optional[int] = None


@dataclass
class Persona:
    code: str
    name: str
    slogan: str
    axes: List[AxisResult]
    roles: List[Role] = field(default_factory=list)
    tier: Optional[Tier] = None
    tips: List[str] = field(default_factory=list)
    locked: bool = False  # 没有订单，人格待解锁


def _load() -> dict:
    return json.loads(PERSONA_FILE.read_text(encoding="utf-8"))


def _ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


# 麦门角色：按顺序检查，取前 MAX_ROLES 个命中的。
# 每条规则：(角色名, 是否命中, 依据)。文案只描述事实，不鼓励过量或不健康的饮食。
RoleRule = Tuple[str, Callable[[Features], bool], Callable[[Features], str]]
ROLE_RULES: List[RoleRule] = [
    ("节气收集家", lambda f: len(f.solar_terms) >= 12,
     lambda f: f"已集齐 {len(f.solar_terms)}/{len(SOLAR_TERMS)} 枚节气门票"),
    ("早八元气派", lambda f: f.order_count >= 3 and _ratio(f.workday_breakfast, f.order_count) >= 0.5,
     lambda f: f"{f.workday_breakfast} 单是工作日的早餐"),
    ("周末犒劳派", lambda f: f.order_count >= 3 and (f.weekend_share or 0) >= 60,
     lambda f: f"{f.weekend_share}% 的订单留给了周末"),
    ("券包管理大师", lambda f: f.detail_count >= 3 and (f.coupon_rate or 0) >= 60,
     lambda f: f"{f.coupon_rate}% 的订单用了券"),
    ("分享担当", lambda f: f.order_count >= 3 and _ratio(f.share_orders, f.order_count) >= 0.4,
     lambda f: f"{f.share_orders} 单一次点了 3 份以上主食"),
    ("堂食仪式感", lambda f: f.order_count >= 3 and _ratio(f.scene_counts.get("堂食", 0), f.order_count) >= 0.5,
     lambda f: f"{f.scene_counts.get('堂食', 0)} 单选择在店里坐下来吃"),
    ("得来速车手", lambda f: f.order_count >= 2 and _ratio(f.scene_counts.get("得来速", 0), f.order_count) >= 0.3,
     lambda f: f"{f.scene_counts.get('得来速', 0)} 单走的是得来速车道"),
    ("团餐组织者", lambda f: f.scene_counts.get("团餐", 0) >= 1,
     lambda f: f"组织过 {f.scene_counts.get('团餐', 0)} 次企业团餐"),
    ("咖啡搭子", lambda f: f.order_count >= 3 and _ratio(f.coffee_orders, f.order_count) >= 0.4,
     lambda f: f"{f.coffee_orders} 单里都有一杯咖啡"),
    ("甜品鉴赏家", lambda f: f.order_count >= 3 and _ratio(f.dessert_orders, f.order_count) >= 0.4,
     lambda f: f"{f.dessert_orders} 单里都有甜品"),
    ("无糖主义", lambda f: f.drink_count >= 3 and _ratio(f.zero_sugar_drinks, f.drink_count) >= 0.5,
     lambda f: f"{f.zero_sugar_drinks}/{f.drink_count} 杯饮品选了无糖"),
    ("蛋白质搭子", lambda f: (f.avg_protein or 0) >= 30,
     lambda f: f"平均每单约 {f.avg_protein} 克蛋白质"),
    ("一店到底", lambda f: f.order_count >= 5 and f.store_count == 1,
     lambda f: f"最近 {f.order_count} 单都在同一家店"),
    ("门店收集家", lambda f: f.store_count >= 4,
     lambda f: f"最近去过 {f.store_count} 家不同的门店"),
    ("积分玩家", lambda f: (f.mall_count or 0) >= 3 or f.other_prizes >= 3,
     lambda f: f"积分兑换 {f.mall_count or 0} 次，抽中 {f.other_prizes} 个奖品"),
    ("麦门常驻", lambda f: (f.per_month or 0) >= 6,
     lambda f: f"平均每月约 {f.per_month:g} 单"),
    ("尝鲜先锋", lambda f: f.distinct_food_count >= 10,
     lambda f: f"最近吃过 {f.distinct_food_count} 种不同的餐品"),
    ("一人食达人", lambda f: f.order_count >= 5 and _ratio(f.solo_orders, f.order_count) >= 0.8,
     lambda f: f"{f.solo_orders}/{f.order_count} 单是一人份"),
]
DEFAULT_ROLE = Role("麦门探索者", "每一单都在丰富你的麦门档案")

# 积分段位：按累计获得的积分划分
TIERS = [(8000, "传奇"), (3000, "元老"), (1000, "资深"), (300, "常客"), (0, "萌新")]


def build(f: Features) -> Persona:
    cfg = _load()
    axes = _axes(f, cfg)
    roles = [Role(name, ev(f)) for name, hit, ev in ROLE_RULES if hit(f)][:MAX_ROLES]
    if f.order_count == 0:
        return Persona(code="？？？？", name="麦门新朋友", slogan="再点几单，你的麦门人格就会浮出水面。",
                       axes=axes, roles=roles, tier=_tier(f), tips=_tips(f), locked=True)
    code = "".join(a.char for a in axes)
    t = cfg["types"][code]
    return Persona(code=code, name=t["name"], slogan=t["slogan"], axes=axes,
                   roles=roles or [DEFAULT_ROLE], tier=_tier(f), tips=_tips(f))


def _axes(f: Features, cfg: dict) -> List[AxisResult]:
    n = f.order_count
    thrift_parts = []
    if f.coupon_rate is not None:
        thrift_parts.append(f"{f.coupon_rate}% 的订单用了券")
    if f.points_ratio is not None:
        thrift_parts.append(f"积分利用率 {f.points_ratio}%")
    evidence = {
        "time": f"最近 {n} 单中有 {_count(f.breakfast_score, n)} 单在 10:30 前下单" if n else "数据不足",
        "channel": f"最近 {n} 单中有 {_count(f.delivery_score, n)} 单是外送" if n else "数据不足",
        "taste": (f"{f.loyalty_score}% 的订单里有回头单品，共吃过 {f.distinct_food_count} 种餐品"
                  if f.loyalty_score is not None else "订单太少，暂时无法判断"),
        "points": "，".join(thrift_parts) if f.thrift_score is not None else "暂无用券和积分记录",
    }
    scores = {"time": f.breakfast_score, "channel": f.delivery_score,
              "taste": f.loyalty_score, "points": f.thrift_score}
    axes = []
    for ax in cfg["axes"]:
        score = scores[ax["id"]]
        # 数据不足时默认落在右侧（正餐 / 到店 / 尝鲜 / 随性）
        left_side = score is not None and score >= 50
        axes.append(AxisResult(
            id=ax["id"], left=ax["left"], right=ax["right"], score=score,
            char=ax["chars"][0 if left_side else 1],
            leaning=ax["left"] if left_side else ax["right"],
            evidence=evidence[ax["id"]],
        ))
    return axes


def type_from_scores(scores: Dict[str, Optional[int]]) -> Tuple[str, dict, List[str]]:
    """只根据四个维度得分判定人格，供分享码使用。返回 (人格代码, 文案, 每个维度落在哪一侧)。"""
    cfg = _load()
    code, leanings = "", []
    for ax in cfg["axes"]:
        score = scores.get(ax["id"])
        left_side = score is not None and score >= 50
        code += ax["chars"][0 if left_side else 1]
        leanings.append(ax["left"] if left_side else ax["right"])
    return code, cfg["types"][code], leanings


def _tier(f: Features) -> Optional[Tier]:
    total = f.points.get("accumulative")
    if total is None:
        return None
    for i, (threshold, name) in enumerate(TIERS):
        if total >= threshold:
            if i == 0:
                return Tier(name, int(total))
            next_threshold, next_name = TIERS[i - 1]
            return Tier(name, int(total), next_name, int(next_threshold - total))
    return None


def _count(score: Optional[int], n: int) -> int:
    return int(round((score or 0) * n / 100))


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _tips(f: Features) -> List[str]:
    tips = []
    expiring = f.points.get("expiring_this_month", 0)
    if expiring > 0:
        tips.append(f"本月有 {_fmt(expiring)} 积分即将过期，记得在麦当劳 App 里用掉")
    if f.coupons_expiring_today:
        tips.append(f"券包里有 {f.coupons_expiring_today} 张券今天到期")
    tips.extend(f.notes)
    return tips
