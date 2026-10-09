"""命令行入口：python3 scripts/run.py {card,match,check}"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import collect, features, persona, render, share_code
from .match import match as do_match
from .mcp_client import MCPClient, MCPError, load_token
from .paths import CACHE_FILE, OUT_DIR


def _log(msg: str) -> None:
    print(f"  · {msg}", file=sys.stderr)


def _load(args) -> Tuple[features.Features, str]:
    bundle = collect.get_bundle(
        demo=args.demo,
        input_path=args.input,
        use_cache=args.cached,
        client_factory=lambda: MCPClient(load_token()),
        log=_log,
    )
    source = bundle.get("_meta", {}).get("source", "live")
    return features.compute(bundle), source


def _profile(f: features.Features) -> share_code.ShareProfile:
    return share_code.ShareProfile(
        scores={"time": f.breakfast_score, "channel": f.delivery_score,
                "taste": f.loyalty_score, "points": f.thrift_score},
        category_shares=f.category_shares,
        favorite_codes=[code for code, _ in f.top_foods],
    )


def _write(out_dir: str, stem: str, svg: str, title: str, open_it: bool) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.svg").write_text(svg, encoding="utf-8")
    page = out / f"{stem}.html"
    page.write_text(render.html_page(svg, title, f"{stem}.png"), encoding="utf-8")
    if open_it:
        webbrowser.open(page.resolve().as_uri())
    return page


def _bar(score: Optional[int]) -> str:
    if score is None:
        return "  数据不足  "
    n = int(round(score / 10))
    return "█" * n + "░" * (10 - n)


def _pct_text(counts: Dict[str, int]) -> str:
    total = sum(counts.values())
    return " · ".join(f"{k} {round(v * 100 / total)}%" for k, v in counts.items()) if total else "—"


def cmd_card(args) -> int:
    f, source = _load(args)
    p = persona.build(f)
    code = share_code.encode(_profile(f))

    lines: List[str] = []
    if source == "demo":
        lines.append("【演示数据】以下结果来自虚构数据\n")
    lines += [f"你的麦门人格：{p.code} · {p.name}", f"  {p.slogan}"]
    if p.tier:
        tier = f"积分段位：{p.tier.name}（累计 {p.tier.points} 分"
        tier += f"，距{p.tier.next_name}还差 {p.tier.gap} 分）" if p.tier.next_name else "）"
        lines.append(tier)

    if not p.locked:
        span = f"，{f.first_date} ~ {f.last_date}" if f.first_date else ""
        lines += ["", f"四维画像（基于最近 {f.order_count} 单{span}，置信度 {f.confidence}）："]
        for ax in p.axes:
            lines.append(f"  {ax.left:<4} {_bar(ax.score)} {ax.right:<4} → {ax.leaning}")
            lines.append(f"       {ax.evidence}")

    if p.roles:
        lines += ["", "麦门角色："]
        lines += [f"  {i}. {r.name}：{r.evidence}" for i, r in enumerate(p.roles, 1)]

    if f.order_count:
        lines += ["", "我的麦当劳时间："]
        lines.append(f"  最常出没：{features.favorite_slot(f)}")
        lines.append(f"  时段分布：{_pct_text(f.period_counts)}")
        freq = f"  工作日 {100 - (f.weekend_share or 0)}% · 周末 {f.weekend_share or 0}%"
        lines.append(freq + (f" · 平均每月约 {f.per_month:g} 单" if f.per_month is not None else ""))
        lines += ["", "场景与口味："]
        lines.append(f"  取餐方式：{_pct_text(f.scene_counts)}")
        lines.append(f"  品类偏好：{_pct_text(f.category_shares)}")

    lines += ["", "麦门档案："]
    if f.favorite_food:
        lines.append(f"  本命单品：{f.favorite_food[1]}（出现在 {f.favorite_food[2]} 单里）")
    if f.favorite_drink:
        lines.append(f"  本命饮品：{f.favorite_drink[1]}")
    if f.avg_kcal:
        lines.append(f"  平均每单：约 {f.avg_kcal} 千卡，蛋白质约 {f.avg_protein} 克（按可识别餐品计算，覆盖 {f.kcal_coverage}%）")
    if f.coupon_rate is not None:
        discount = f"，用券时平均优惠 {f.avg_discount}%" if f.avg_discount else ""
        lines.append(f"  用券订单：{f.coupon_rate}%{discount}")
    lines.append(f"  节气门票：{len(f.solar_terms)}/24" + (f"（{'、'.join(f.solar_terms)}）" if f.solar_terms else ""))
    if f.order_count:
        lines.append(f"  门店足迹：{f.store_count} 家")
    for tip in p.tips:
        lines.append(f"提示：{tip}")
    if not p.locked:
        lines += ["", f"你的饭搭子码：{code}",
                  f"发给朋友，让 TA 在装了本 Skill 的 Agent 里说「和 {code} 测测饭搭子匹配度」"]
    print("\n".join(lines))

    svg = render.persona_svg(p, f, code, nickname=args.name, source=source)
    page = _write(args.out, "persona-card", svg, f"{p.name} · 麦门人格卡", args.open)
    print(f"\n卡片已生成：{page.resolve()}")
    return 0


def cmd_match(args) -> int:
    try:
        friend = share_code.decode(args.codes[-1])
        mine_code = args.codes[0] if len(args.codes) == 2 else None
        food_names: Dict[str, str] = {}
        if mine_code:
            me = share_code.decode(mine_code)
            label_a, label_b = args.name or "A", args.friend_name or "B"
        else:
            f, source = _load(args)
            if source == "demo":
                print("【演示数据】你这一方使用的是虚构数据\n")
            if f.order_count == 0:
                print("没有读取到你的历史订单，无法匹配。可以传入两个分享码直接比较。")
                return 1
            me = _profile(f)
            food_names = dict(f.top_foods)
            label_a, label_b = args.name or "你", args.friend_name or "TA"
    except share_code.ShareCodeError as e:
        print(f"分享码有问题：{e}")
        return 1

    m = do_match(me, friend, label_a, label_b, food_names)
    lines = [
        f"饭搭子匹配度：{m.score}% · {m.relation}",
        f"  {m.relation_desc}",
        "",
        f"  {m.a.label}：{m.a.code} · {m.a.name}",
        f"  {m.b.label}：{m.b.code} · {m.b.name}",
        "",
    ]
    if m.same:
        lines.append("共同点：" + "，".join(m.same))
    for d in m.different:
        lines.append(f"不同点：{d}")
    lines.append(f"共同点单建议：{m.suggestion}")
    print("\n".join(lines))

    page = _write(args.out, "match-card", render.match_svg(m), f"{m.relation} · 饭搭子匹配", args.open)
    print(f"\n匹配卡已生成：{page.resolve()}")
    return 0


def cmd_check(args) -> int:
    client = MCPClient(load_token())
    info = client.initialize()
    tools = {t["name"] for t in client.list_tools()}
    server = info.get("serverInfo", {})
    print(f"已连接：{server.get('name', 'mcd-mcp')} {server.get('version', '')}，共 {len(tools)} 个工具")
    missing = [t for t in collect.READ_ONLY_TOOLS if t not in tools]
    if missing:
        print("缺少本项目需要的工具：" + "、".join(missing))
        return 1
    print("本项目需要的只读工具全部可用：" + "、".join(collect.READ_ONLY_TOOLS))
    return 0


def _add_source_args(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true", help="使用仓库自带的虚构数据，无需 Token")
    g.add_argument("--input", metavar="FILE", help="从 JSON 文件读取数据（例如由 Agent 调用 MCP 后保存）")
    g.add_argument("--cached", action="store_true", help=f"使用上次拉取的本地缓存 {CACHE_FILE}")
    p.add_argument("--name", help="卡片上显示的昵称")
    p.add_argument("--out", default=str(OUT_DIR), help=f"输出目录，默认 {OUT_DIR}")
    p.add_argument("--open", action="store_true", help="生成后用浏览器打开")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mcd_persona", description="麦门人格卡 + 饭搭子匹配（基于麦当劳 MCP）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_card = sub.add_parser("card", help="生成我的麦门人格卡")
    _add_source_args(p_card)
    p_card.set_defaults(func=cmd_card)

    p_match = sub.add_parser("match", help="和朋友的饭搭子码做匹配")
    p_match.add_argument("codes", nargs="+", metavar="CODE", help="朋友的分享码；传两个码则直接比较两者")
    p_match.add_argument("--friend-name", help="对方的昵称")
    _add_source_args(p_match)
    p_match.set_defaults(func=cmd_match)

    p_check = sub.add_parser("check", help="检查 Token 和 MCP 连接")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if args.cmd == "match" and len(args.codes) > 2:
        parser.error("最多传入两个分享码")
    try:
        return args.func(args)
    except MCPError as e:
        print(f"出错了：{e}", file=sys.stderr)
        return 2
