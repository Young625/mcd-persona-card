"""餐品分类与营养数据匹配。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

CATEGORIES = ["主食", "小食", "甜品", "饮品", "其他"]
FOOD_CATEGORIES = ("主食", "小食", "甜品")

# 按顺序匹配，先命中者优先（例如“酥酥多笋卷”需要先于“卷”被识别为小食）
_RULES = [
    ("饮品", ["可乐", "咖", "拿铁", "豆浆", "牛奶", "奶茶", "茶", "果汁", "雪碧", "芬达", "美式", "饮", "柠檬", "橙汁", "水"]),
    ("甜品", ["派", "麦旋风", "新地", "冰淇淋", "圆筒", "甜筒", "蛋挞", "麦芬", "雪糕", "甜品"]),
    ("小食", ["薯条", "薯饼", "鸡块", "麦乐鸡", "鸡翅", "V翅", "脆汁鸡", "玉米杯", "笋卷", "鸡米花", "沙拉", "小食"]),
    ("主食", ["堡", "麦满分", "卷", "饭", "粥", "松饼", "鸡扒", "吉士", "汉堡", "三明治", "意面",
              "麦香鸡", "麦香鱼", "板烧", "猪柳", "鸡腿"]),
]


_COFFEE = ("咖", "拿铁", "美式", "摩卡", "卡布", "澳白")
_ZERO_SUGAR = ("无糖", "零度", "0糖", "零糖", "zero", "Zero", "ZERO")


def is_coffee(name: str) -> bool:
    return any(k in name for k in _COFFEE)


def is_zero_sugar(name: str) -> bool:
    return any(k in name for k in _ZERO_SUGAR)


def categorize(name: str) -> str:
    for category, keywords in _RULES:
        if any(k in name for k in keywords):
            return category
    return "其他"


def normalize_name(name: str) -> str:
    name = re.sub(r"[（(][^）)]*[）)]", "", name or "")
    return re.sub(r"\s+", "", name)


@dataclass(frozen=True)
class Nutrition:
    name: str
    kcal: float
    protein: float
    fat: float
    carbohydrate: float
    sodium: float


def parse_nutrition(data) -> List[Nutrition]:
    """解析 list-nutrition-foods 的返回。

    实测返回的是紧凑表格文本：
        [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
          猪柳麦满分,null,1288,308,16,16,24,781,213
    也兼容对象列表形式。
    """
    if isinstance(data, dict):
        data = data.get("data", data)
    if isinstance(data, list):
        out = []
        for row in data:
            try:
                out.append(Nutrition(
                    name=normalize_name(str(row["productName"])),
                    kcal=float(row["energyKcal"]),
                    protein=float(row.get("protein") or 0),
                    fat=float(row.get("fat") or 0),
                    carbohydrate=float(row.get("carbohydrate") or 0),
                    sodium=float(row.get("sodium") or 0),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out
    if not isinstance(data, str):
        return []

    lines = data.strip().splitlines()
    if not lines:
        return []
    header = re.search(r"\{([^}]*)\}", lines[0])
    if not header:
        return []
    fields = [f.strip() for f in header.group(1).split(",")]
    n = len(fields)
    out = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        # 餐品名里可能有逗号，所以从右往左切
        parts = line.rsplit(",", n - 1)
        if len(parts) != n:
            continue
        row = dict(zip(fields, parts))
        try:
            out.append(Nutrition(
                name=normalize_name(row["productName"]),
                kcal=float(row["energyKcal"]),
                protein=_num(row.get("protein")),
                fat=_num(row.get("fat")),
                carbohydrate=_num(row.get("carbohydrate")),
                sodium=_num(row.get("sodium")),
            ))
        except (KeyError, ValueError):
            continue
    return out


def _num(v: Optional[str]) -> float:
    try:
        return float(v) if v not in (None, "", "null") else 0.0
    except ValueError:
        return 0.0


class NutritionIndex:
    def __init__(self, items: List[Nutrition]):
        self._by_name: Dict[str, Nutrition] = {i.name: i for i in items}
        # 长名优先，避免“薯条”抢先匹配到“中薯条”之类
        self._names = sorted(self._by_name, key=len, reverse=True)

    def __len__(self) -> int:
        return len(self._by_name)

    def lookup(self, name: str) -> Optional[Nutrition]:
        key = normalize_name(name)
        if not key:
            return None
        if key in self._by_name:
            return self._by_name[key]
        # 订单名包含营养表里的完整名字，例如“麦辣鸡腿汉堡(新)”
        for candidate in self._names:
            if len(candidate) >= 3 and candidate in key:
                return self._by_name[candidate]
        # 营养表名字包含订单名，例如订单“板烧鸡腿堡” vs 表“板烧鸡腿堡(原味)”
        for candidate in self._names:
            if len(key) >= 3 and key in candidate:
                return self._by_name[candidate]
        return None
