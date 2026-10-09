"""把人格结果和匹配结果渲染成 SVG 卡片，并包一层可下载 PNG 的 HTML。"""

from __future__ import annotations

import html
from typing import List, Optional

from .features import PERIODS, SOLAR_TERMS, Features, favorite_slot
from .match import MatchResult
from .persona import Persona

W = 720
FONT = "'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',sans-serif"
MONO = "'SF Mono',Menlo,Consolas,monospace"
RED = "#D62828"
RED_DARK = "#A61E1E"
YELLOW = "#FFBC0D"
CREAM = "#FFF8E8"
INK = "#2B2118"
MUTED = "#7A6A58"
LINE = "#EADFC8"
REPO = "github.com/Young625/mcd-persona-card"


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def _text_width(s: str, size: float) -> float:
    return sum(size if ord(ch) > 0x2E80 else size * 0.56 for ch in s)


def wrap(s: str, size: float, max_width: float, max_lines: int = 3) -> List[str]:
    lines, cur = [], ""
    for ch in s:
        if _text_width(cur + ch, size) > max_width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def truncate(s: str, size: float, max_width: float) -> str:
    return wrap(s, size, max_width, max_lines=1)[0] if s else s


def _t(x, y, s, size=24, fill=INK, weight=400, anchor="start", family=FONT, extra="") -> str:
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" {extra}>{esc(s)}</text>')


# ---------------- 人格卡 ----------------

SEG_COLORS = ["#D62828", "#FFBC0D", "#F28C28", "#7A5C3E", "#C9B79C"]
M = 48  # 左右边距


class _Canvas:
    """按从上到下的顺序堆叠各个板块。"""

    def __init__(self) -> None:
        self.parts: List[str] = []
        self.y = 0.0
        self._clip = 0

    def add(self, s: str) -> None:
        self.parts.append(s)

    def title(self, text: str) -> None:
        self.y += 56
        self.add(_t(M, self.y, text, 26, INK, 700))
        self.y += 20

    def clip_id(self) -> str:
        self._clip += 1
        return f"c{self._clip}"


def persona_svg(p: Persona, f: Features, share_code: str, nickname: Optional[str] = None,
                source: str = "live") -> str:
    c = _Canvas()
    _header(c, p, f, nickname, source)
    if not p.locked:
        _axes_section(c, p)
    if p.roles:
        _roles_section(c, p)
    if f.order_count:
        _time_section(c, f)
        _scene_section(c, f)
    _archive_section(c, p, f)
    _share_section(c, p, share_code)
    c.y += 44
    c.add(_t(W / 2, c.y, f"数据来自麦当劳 MCP · {REPO}", 16, MUTED, 400, "middle"))
    c.add(_t(W / 2, c.y + 26, "粉丝创意作品，非麦当劳官方产品 · 结果仅供娱乐", 16, MUTED, 400, "middle"))
    return _svg(c.parts, int(c.y + 56))


def _header(c: _Canvas, p: Persona, f: Features, nickname: Optional[str], source: str) -> None:
    body: List[str] = []
    title = f"{nickname} 的麦门人格" if nickname else "我的麦门人格"
    body.append(_t(M, 76, truncate(title, 26, 480), 26, YELLOW, 600))
    if source == "demo":
        body.append(f'<rect x="{W - 148}" y="50" width="100" height="36" rx="18" fill="{YELLOW}"/>')
        body.append(_t(W - 98, 75, "演示数据", 18, RED_DARK, 700, "middle"))
    meta = f"置信度 {f.confidence} · 基于最近 {f.order_count} 单" if f.order_count else "还没有订单记录"
    body.append(_t(M, 110, meta, 18, "#FFD9A0"))

    box, gap = 120, 20
    x0 = (W - (4 * box + 3 * gap)) / 2
    for i, ch in enumerate(p.code):
        x = x0 + i * (box + gap)
        body.append(f'<rect x="{x}" y="138" width="{box}" height="{box}" rx="24" fill="{CREAM}"/>')
        body.append(_t(x + box / 2, 138 + 84, ch, 68, RED if not p.locked else MUTED, 800, "middle"))
    body.append(_t(W / 2, 334, p.name, 48, "#FFFFFF", 800, "middle"))
    y = 378
    for line in wrap(p.slogan, 24, W - 120, 2):
        body.append(_t(W / 2, y, line, 24, "#FFE9B0", 400, "middle"))
        y += 34
    if p.tier:
        label = f"积分段位 · {p.tier.name}"
        if p.tier.next_name:
            label += f" · 距{p.tier.next_name}还差 {p.tier.gap} 分"
        bw = _text_width(label, 20) + 48
        body.append(f'<rect x="{(W - bw) / 2}" y="{y - 4}" width="{bw}" height="42" rx="21" fill="{RED_DARK}"/>')
        body.append(_t(W / 2, y + 24, label, 20, YELLOW, 700, "middle"))
        y += 42
    head_h = y + 28
    c.add(f'<rect x="0" y="0" width="{W}" height="{head_h}" fill="{RED}"/>')
    c.add(f'<clipPath id="hd"><rect x="0" y="0" width="{W}" height="{head_h}"/></clipPath>'
          f'<circle cx="{W - 40}" cy="40" r="140" fill="{RED_DARK}" opacity="0.5" clip-path="url(#hd)"/>')
    c.parts.extend(body)
    c.y = head_h - 8


def _axes_section(c: _Canvas, p: Persona) -> None:
    c.title("四维画像")
    bar_x, bar_w = 160, W - 320
    for ax in p.axes:
        c.y += 52
        y = c.y
        left_on = ax.leaning == ax.left
        c.add(_t(M, y + 8, ax.left, 22, RED if left_on else MUTED, 700 if left_on else 400))
        c.add(_t(W - M, y + 8, ax.right, 22, MUTED if left_on else RED, 400 if left_on else 700, "end"))
        c.add(f'<rect x="{bar_x}" y="{y - 8}" width="{bar_w}" height="16" rx="8" fill="{LINE}"/>')
        mid = bar_x + bar_w / 2
        if ax.score is not None:
            pos = bar_x + bar_w * (1 - ax.score / 100)
            lo, hi = sorted((mid, pos))
            c.add(f'<rect x="{lo}" y="{y - 8}" width="{max(hi - lo, 0.1)}" height="16" fill="{YELLOW}"/>')
            c.add(f'<circle cx="{pos}" cy="{y}" r="14" fill="{RED}" stroke="#fff" stroke-width="4"/>')
            label = f"{ax.score}%" if left_on else f"{100 - ax.score}%"
            c.add(_t(pos, y - 22, label, 16, RED, 700, "middle"))
        else:
            c.add(_t(mid, y + 7, "数据不足", 18, MUTED, 400, "middle"))
        c.add(f'<line x1="{mid}" y1="{y - 14}" x2="{mid}" y2="{y + 14}" '
              f'stroke="{MUTED}" stroke-width="2" stroke-dasharray="3 3"/>')
    c.y += 20


def _roles_section(c: _Canvas, p: Persona) -> None:
    c.title("麦门角色")
    for i, role in enumerate(p.roles):
        y = c.y + 4
        c.add(f'<rect x="{M}" y="{y}" width="{W - 2 * M}" height="80" rx="18" fill="#FFFFFF" '
              f'stroke="{LINE}" stroke-width="2"/>')
        c.add(f'<circle cx="{M + 42}" cy="{y + 40}" r="22" fill="{YELLOW}"/>')
        c.add(_t(M + 42, y + 49, str(i + 1), 24, RED_DARK, 800, "middle"))
        c.add(_t(M + 84, y + 36, role.name, 26, INK, 700))
        c.add(_t(M + 84, y + 64, truncate(role.evidence, 18, W - 2 * M - 110), 18, MUTED))
        c.y = y + 80 + 8


def _time_section(c: _Canvas, f: Features) -> None:
    c.title("我的麦当劳时间")
    c.y += 20
    c.add(_t(M, c.y, f"最常出没：{favorite_slot(f)}", 26, RED, 700))
    c.y += 34
    sub = f"工作日 {100 - (f.weekend_share or 0)}% · 周末 {f.weekend_share or 0}%"
    if f.per_month is not None:
        sub += f" · 平均每月约 {f.per_month:g} 单"
    c.add(_t(M, c.y, sub, 18, MUTED))
    # 五个时段的柱状图
    c.y += 24
    max_h, base = 96, c.y + 24 + 96
    col_w = (W - 2 * M) / len(PERIODS)
    top = max(f.period_counts.values()) if f.period_counts else 1
    for i, period in enumerate(PERIODS):
        n = f.period_counts.get(period, 0)
        cx = M + col_w * (i + 0.5)
        h = max_h * n / top if n else 4
        color = RED if period in f.top_periods else YELLOW if n else LINE
        c.add(f'<rect x="{cx - 26}" y="{base - h}" width="52" height="{h}" rx="10" fill="{color}"/>')
        if n:
            c.add(_t(cx, base - h - 10, f"{n} 单", 16, INK, 700, "middle"))
        c.add(_t(cx, base + 28, period, 18, MUTED, 400, "middle"))
    c.y = base + 36


def _stacked_bar(c: _Canvas, label: str, data: dict) -> None:
    total = sum(data.values())
    if not total:
        return
    c.y += 30
    c.add(_t(M, c.y, label, 18, MUTED))
    c.y += 14
    cid = c.clip_id()
    width = W - 2 * M
    c.add(f'<clipPath id="{cid}"><rect x="{M}" y="{c.y}" width="{width}" height="24" rx="12"/></clipPath>')
    x = M
    items = list(data.items())
    for i, (_, v) in enumerate(items):
        w = width * v / total
        c.add(f'<rect x="{x}" y="{c.y}" width="{w}" height="24" fill="{SEG_COLORS[i % len(SEG_COLORS)]}" '
              f'clip-path="url({"#" + cid})"/>')
        x += w
    c.y += 48
    lx = M
    for i, (k, v) in enumerate(items):
        text = f"{k} {round(v * 100 / total)}%"
        tw = _text_width(text, 18) + 30
        if lx + tw > W - M:
            lx = M
            c.y += 30
        c.add(f'<circle cx="{lx + 7}" cy="{c.y - 6}" r="7" fill="{SEG_COLORS[i % len(SEG_COLORS)]}"/>')
        c.add(_t(lx + 20, c.y, text, 18, INK))
        lx += tw + 12
    c.y += 12


def _scene_section(c: _Canvas, f: Features) -> None:
    c.title("场景与口味")
    _stacked_bar(c, "取餐方式", f.scene_counts)
    _stacked_bar(c, "品类偏好（按份数）", {k: v for k, v in f.category_shares.items() if v})
    c.y += 4


def _archive_section(c: _Canvas, p: Persona, f: Features) -> None:
    c.title("麦门档案")
    last_term = f"最近一枚：{f.solar_terms[-1]}" if f.solar_terms else "下单后有机会获得"
    if f.order_count:
        cells = [
            ("本命单品", f.favorite_food[1] if f.favorite_food else "—",
             f"出现在 {f.favorite_food[2]} 单里" if f.favorite_food else ""),
            ("本命饮品", f.favorite_drink[1] if f.favorite_drink else "—",
             f"出现在 {f.favorite_drink[2]} 单里" if f.favorite_drink else ""),
            ("平均每单", f"约 {f.avg_kcal} 千卡" if f.avg_kcal else "—",
             f"蛋白质约 {f.avg_protein} 克 · 覆盖 {f.kcal_coverage}%" if f.avg_kcal else "营养数据覆盖不足"),
            ("用券订单", f"{f.coupon_rate}%" if f.coupon_rate is not None else "—",
             f"用券时平均优惠 {f.avg_discount}%" if f.avg_discount else "基于订单详情"),
            ("节气门票", f"{len(f.solar_terms)}/{len(SOLAR_TERMS)}", last_term),
            ("门店足迹", f"{f.store_count} 家", f"共 {f.distinct_food_count} 种餐品"),
        ]
    else:
        cells = [
            ("节气门票", f"{len(f.solar_terms)}/{len(SOLAR_TERMS)}", last_term),
            ("累计积分", f"{p.tier.points}" if p.tier else "—", f"段位：{p.tier.name}" if p.tier else ""),
            ("券包", f"{f.coupon_wallet} 张" if f.coupon_wallet is not None else "—", "可在麦当劳 App 查看"),
            ("积分兑换", f"{f.mall_count} 次" if f.mall_count is not None else "—", "近一年"),
        ]
    cw, ch, cg = (W - 2 * M - 20) / 2, 112, 20
    c.y += 4
    for i, (label, value, sub) in enumerate(cells):
        cx = M + (i % 2) * (cw + cg)
        cy = c.y + (i // 2) * (ch + 16)
        c.add(f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="18" fill="#FFFFFF" stroke="{LINE}" stroke-width="2"/>')
        c.add(_t(cx + 22, cy + 34, label, 18, MUTED))
        c.add(_t(cx + 22, cy + 70, truncate(value, 28, cw - 44), 28, INK, 700))
        if sub:
            c.add(_t(cx + 22, cy + 96, truncate(sub, 16, cw - 44), 16, MUTED))
    rows = (len(cells) + 1) // 2
    c.y += rows * (ch + 16) - 16


def _share_section(c: _Canvas, p: Persona, share_code: str) -> None:
    c.y += 32
    y = c.y
    c.add(f'<rect x="{M}" y="{y}" width="{W - 2 * M}" height="138" rx="20" fill="{INK}"/>')
    if p.locked:
        c.add(_t(M + 28, y + 52, "饭搭子码待解锁", 22, YELLOW, 700))
        c.add(_t(M + 28, y + 92, "点几单之后再来，就能和朋友测匹配度了", 18, "#BFAF98"))
    else:
        c.add(_t(M + 28, y + 40, "我的饭搭子码 · 发给朋友测测匹配度", 20, YELLOW, 700))
        c.add(_t(M + 28, y + 84, truncate(share_code, 24, W - 2 * M - 56), 24, "#FFFFFF", 600, family=MONO))
        c.add(_t(M + 28, y + 118, "在 Agent 里说：和这个码测测饭搭子匹配度", 17, "#BFAF98"))
    c.y = y + 138


def _svg(parts: List[str], height: int) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}">'
            f'<rect width="{W}" height="{height}" fill="{CREAM}"/>' + "".join(parts) + "</svg>")


# ---------------- 匹配卡 ----------------

def match_svg(m: MatchResult) -> str:
    parts: List[str] = []
    head_h = 330
    parts.append(f'<rect x="0" y="0" width="{W}" height="{head_h}" fill="{RED}"/>')
    parts.append(f'<clipPath id="mh"><rect x="0" y="0" width="{W}" height="{head_h}"/></clipPath>'
                 f'<circle cx="40" cy="{head_h}" r="160" fill="{RED_DARK}" opacity="0.5" clip-path="url(#mh)"/>')
    parts.append(_t(W / 2, 70, "饭搭子匹配度", 26, YELLOW, 700, "middle"))
    parts.append(_t(W / 2, 190, f"{m.score}%", 112, "#FFFFFF", 800, "middle"))
    parts.append(_t(W / 2, 250, m.relation, 40, YELLOW, 800, "middle"))
    for i, line in enumerate(wrap(m.relation_desc, 22, W - 120, 2)):
        parts.append(_t(W / 2, 292 + i * 30, line, 22, "#FFE9B0", 400, "middle"))
    y = head_h + 40

    cw = (W - 96 - 20) / 2
    for i, side in enumerate((m.a, m.b)):
        cx = 48 + i * (cw + 20)
        parts.append(f'<rect x="{cx}" y="{y}" width="{cw}" height="150" rx="20" fill="#FFFFFF" stroke="{LINE}" stroke-width="2"/>')
        parts.append(_t(cx + cw / 2, y + 40, truncate(side.label, 22, cw - 40), 22, MUTED, 400, "middle"))
        parts.append(_t(cx + cw / 2, y + 92, side.code, 44, RED, 800, "middle"))
        parts.append(_t(cx + cw / 2, y + 130, side.name, 24, INK, 700, "middle"))
    y += 150 + 50

    def section(title: str, lines: List[str], y: float) -> float:
        if not lines:
            return y
        parts.append(_t(48, y, title, 24, INK, 700))
        y += 12
        for line in lines:
            for j, seg in enumerate(wrap(line, 20, W - 120, 3)):
                y += 32
                if j == 0:
                    parts.append(f'<circle cx="58" cy="{y - 7}" r="5" fill="{YELLOW}"/>')
                parts.append(_t(76, y, seg, 20, INK))
        return y + 40

    y = section("你们的共同点", m.same, y)
    y = section("你们的不同点", m.different, y)
    y = section("共同点单建议", [m.suggestion], y)

    parts.append(_t(W / 2, y, f"数据来自麦当劳 MCP · {REPO}", 16, MUTED, 400, "middle"))
    parts.append(_t(W / 2, y + 26, "粉丝创意作品，非麦当劳官方产品 · 结果仅供娱乐", 16, MUTED, 400, "middle"))
    return _svg(parts, int(y + 56))


# ---------------- HTML 外壳 ----------------

def html_page(svg: str, title: str, filename: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
  body {{ margin: 0; background: #EFE6D2; font-family: {FONT}; display: flex; flex-direction: column;
         align-items: center; padding: 24px 16px 48px; }}
  .card {{ width: 100%; max-width: {W}px; box-shadow: 0 12px 40px rgba(60,40,10,.18); border-radius: 24px; overflow: hidden; line-height: 0; }}
  .card svg {{ width: 100%; height: auto; }}
  button {{ margin-top: 24px; font: inherit; font-size: 17px; font-weight: 700; color: #2B2118; background: {YELLOW};
           border: 0; border-radius: 999px; padding: 14px 32px; cursor: pointer; }}
  p {{ color: #7A6A58; font-size: 14px; }}
</style>
</head>
<body>
<div class="card" id="card">{svg}</div>
<button id="dl">下载 PNG 图片</button>
<p>本页面在本地生成，不会上传任何数据。</p>
<script>
document.getElementById('dl').addEventListener('click', function () {{
  var svg = document.querySelector('#card svg');
  var w = +svg.getAttribute('width'), h = +svg.getAttribute('height'), scale = 2;
  var xml = new XMLSerializer().serializeToString(svg);
  var img = new Image();
  img.onload = function () {{
    var c = document.createElement('canvas');
    c.width = w * scale; c.height = h * scale;
    var ctx = c.getContext('2d');
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, w, h);
    c.toBlob(function (blob) {{
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = {filename!r};
      a.click();
    }}, 'image/png');
  }};
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
}});
</script>
</body>
</html>
"""
