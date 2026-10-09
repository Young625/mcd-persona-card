"""饭搭子匹配：比较两份分享码，给出匹配度、搭子类型和共同点单建议。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .catalog import CATEGORIES, FOOD_CATEGORIES
from .persona import type_from_scores
from .share_code import AXIS_IDS, ShareProfile

RELATIONS = [
    (4, "灵魂麦搭子", "点餐习惯几乎一模一样，一起去麦当劳连菜单都不用看。"),
    (3, "默契饭友", "大方向一致，只在一个地方不一样，正好互相种草。"),
    (2, "互补拍档", "一半相同一半不同，一起点餐总能发现新组合。"),
    (0, "反差萌组合", "习惯几乎相反，正好带对方解锁全新的吃法。"),
]

DIFF_HINTS = {
    "time": "一个吃早餐一个吃正餐，一天的麦当劳被你们承包了",
    "channel": "一个爱外送一个爱到店，下次轮流做东",
    "taste": "专一派带对方认识经典，尝鲜派负责发现新品",
    "points": "精打细算的那位，记得提醒对方用掉快过期的积分",
}


@dataclass
class Side:
    label: str
    code: str
    name: str
    leanings: List[str]


@dataclass
class MatchResult:
    score: int
    relation: str
    relation_desc: str
    a: Side
    b: Side
    same: List[str] = field(default_factory=list)      # 相同点
    different: List[str] = field(default_factory=list)  # 不同点及建议
    shared_foods: List[str] = field(default_factory=list)
    suggestion: str = ""


def _axis_similarity(a: ShareProfile, b: ShareProfile) -> float:
    diffs = [abs(a.scores[x] - b.scores[x]) for x in AXIS_IDS
             if a.scores.get(x) is not None and b.scores.get(x) is not None]
    return 100 - sum(diffs) / len(diffs) if diffs else 50.0


def _category_similarity(a: ShareProfile, b: ShareProfile) -> float:
    va = [a.category_shares.get(c, 0) for c in CATEGORIES]
    vb = [b.category_shares.get(c, 0) for c in CATEGORIES]
    na, nb = math.sqrt(sum(x * x for x in va)), math.sqrt(sum(x * x for x in vb))
    if not na or not nb:
        return 50.0
    return 100 * sum(x * y for x, y in zip(va, vb)) / (na * nb)


def match(
    a: ShareProfile,
    b: ShareProfile,
    label_a: str = "你",
    label_b: str = "TA",
    food_names: Optional[Dict[str, str]] = None,
) -> MatchResult:
    food_names = food_names or {}
    code_a, type_a, lean_a = type_from_scores(a.scores)
    code_b, type_b, lean_b = type_from_scores(b.scores)

    shared_codes = [c for c in a.favorite_codes if c in b.favorite_codes]
    score = 0.6 * _axis_similarity(a, b) + 0.3 * _category_similarity(a, b) + (10 if shared_codes else 0)
    score = int(round(max(0, min(100, score))))

    same_count = sum(x == y for x, y in zip(code_a, code_b))
    relation, desc = next((r, d) for n, r, d in RELATIONS if same_count >= n)

    result = MatchResult(
        score=score, relation=relation, relation_desc=desc,
        a=Side(label_a, code_a, type_a["name"], lean_a),
        b=Side(label_b, code_b, type_b["name"], lean_b),
    )
    for axis, la, lb in zip(AXIS_IDS, lean_a, lean_b):
        if la == lb:
            result.same.append(f"都是{la}")
        else:
            result.different.append(f"{label_a}是{la}，{label_b}是{lb}：{DIFF_HINTS[axis]}")

    result.shared_foods = [food_names[c] for c in shared_codes if c in food_names]
    result.suggestion = _suggest(a, b, shared_codes, result.shared_foods)
    return result


def _suggest(a: ShareProfile, b: ShareProfile, shared_codes: List[str], shared_names: List[str]) -> str:
    if shared_names:
        return f"你们都爱{'、'.join(shared_names)}，下次一起点准没错。"
    if shared_codes:
        return f"你们有 {len(shared_codes)} 款相同的本命单品，见面对一下暗号吧。"
    combined = {c: a.category_shares.get(c, 0) + b.category_shares.get(c, 0) for c in FOOD_CATEGORIES}
    top = max(combined, key=combined.get)
    if not combined[top]:
        return "数据还不够多，多点几单再来测测。"
    return f"你们都偏爱{top}，下次各点一份自己的本命{top}，换着尝尝。"
