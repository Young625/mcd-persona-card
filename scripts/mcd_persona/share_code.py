"""分享码：只包含统计结果，不含订单、门店、金额等原始数据。

二进制布局（v1）：
    [0]      版本号
    [1..4]   四个维度得分 0-100，255 表示数据不足
    [5..9]   主食/小食/甜品/饮品/其他 占比 0-100
    [10]     本命单品数量 k（0-3）
    [..]     k 个单品编码，各 4 字节无符号整数
    [-1]     CRC32 的低 8 位，用于发现复制错误
编码后形如 MC-AQAeAFAl...
"""

from __future__ import annotations

import base64
import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .catalog import CATEGORIES

PREFIX = "MC-"
VERSION = 1
AXIS_IDS = ("time", "channel", "taste", "points")
UNKNOWN = 255


class ShareCodeError(ValueError):
    pass


@dataclass
class ShareProfile:
    scores: Dict[str, Optional[int]]
    category_shares: Dict[str, int]
    favorite_codes: List[str] = field(default_factory=list)


def encode(profile: ShareProfile) -> str:
    buf = bytearray([VERSION])
    for axis in AXIS_IDS:
        s = profile.scores.get(axis)
        buf.append(UNKNOWN if s is None else max(0, min(100, int(s))))
    for cat in CATEGORIES:
        buf.append(max(0, min(100, int(profile.category_shares.get(cat, 0)))))
    codes = [int(c) for c in profile.favorite_codes if c.isdigit() and int(c) < 2 ** 32][:3]
    buf.append(len(codes))
    for c in codes:
        buf += struct.pack(">I", c)
    buf.append(zlib.crc32(bytes(buf)) & 0xFF)
    return PREFIX + base64.urlsafe_b64encode(bytes(buf)).decode("ascii").rstrip("=")


def decode(code: str) -> ShareProfile:
    text = (code or "").strip()
    if not text.startswith(PREFIX):
        raise ShareCodeError("分享码应该以 MC- 开头")
    body = text[len(PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except (ValueError, base64.binascii.Error):
        raise ShareCodeError("分享码格式不对，可能复制不完整") from None
    if len(raw) < 12:
        raise ShareCodeError("分享码太短，可能复制不完整")
    payload, check = raw[:-1], raw[-1]
    if zlib.crc32(payload) & 0xFF != check:
        raise ShareCodeError("分享码校验失败，可能复制错了")
    if payload[0] != VERSION:
        raise ShareCodeError(f"不支持的分享码版本：{payload[0]}，请升级工具")

    scores = {axis: (None if payload[1 + i] == UNKNOWN else payload[1 + i]) for i, axis in enumerate(AXIS_IDS)}
    shares = {cat: payload[5 + i] for i, cat in enumerate(CATEGORIES)}
    k = payload[10]
    if len(payload) != 11 + 4 * k or k > 3:
        raise ShareCodeError("分享码长度不对，可能复制不完整")
    codes = [str(struct.unpack(">I", payload[11 + 4 * i: 15 + 4 * i])[0]) for i in range(k)]
    return ShareProfile(scores=scores, category_shares=shares, favorite_codes=codes)
