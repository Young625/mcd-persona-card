---
name: mcd-persona-card
description: 麦门人格卡 + 饭搭子匹配。读取用户在麦当劳的最近订单、订单详情、积分、奖品和券包（全部只读），从时段、取餐方式、口味、用券、积分等角度生成可分享的“麦门人格卡”（四维人格 + 麦门角色 + 积分段位）和饭搭子码，并能和朋友的饭搭子码计算匹配度、给出共同点单建议。用户说“生成我的麦门人格”“测测我的麦当劳人格”“我们是不是饭搭子”“和朋友匹配一下”，或发来 MC- 开头的分享码时使用。
---

# 麦门人格卡 + 饭搭子匹配

## 运行方式

所有功能都通过本 Skill 目录下的 `scripts/run.py` 完成，需要 Python 3.9 及以上版本，没有第三方依赖。

下文的 `<SKILL_DIR>` 指本 `SKILL.md` 所在目录，执行时请换成它的**绝对路径**。命令可以在任何工作目录下执行；缓存和卡片统一保存在 `~/.mcd-persona-card/`，不会写进用户当前的项目。

- `--open` 会用浏览器打开卡片，可选；没有图形界面时去掉。
- 卡片固定输出为 `~/.mcd-persona-card/out/persona-card.html` 和 `match-card.html`，再次运行会覆盖。用户想保留多张卡片时，用 `--out <目录>` 另存。

## 安全规则（必须遵守）

- 只允许调用这些只读 Tool：`order-list`、`query-order`、`query-my-account`、`query-my-prizes`、`query-my-coupons`、`mall-order-list`、`list-nutrition-foods`、`now-time-info`。
- **绝不**调用 `create-order`、`cancel-order`、`auto-bind-coupons`、`draw-lottery`、`mall-create-order`、`party-order-create` 等会改变账户状态的 Tool。用户顺口提到时，先说明本 Skill 不做这些事。
- 不要在对话里输出用户的 Token、订单号、账户 ID、门店名称和消费金额（脚本本身也不会输出这些）。

## 生成人格卡

用户明确说要用演示数据时，直接用方式 C；否则按 A → B → C 的顺序选择。

**方式 A：脚本自己连接 MCP**

适用于已设置环境变量 `MCD_MCP_TOKEN`，或 Token 写在 `~/.mcd-persona-card/.env`（格式为 `MCD_MCP_TOKEN=...`）的情况：

```bash
python3 <SKILL_DIR>/scripts/run.py card --open
```

可加 `--name 昵称`，让卡片显示昵称。如果提示找不到 Token，改用方式 B 或 C，**不要让用户把 Token 发到对话里**。

**方式 B：你已经通过 MCP 连接器接入了麦当劳 MCP**

适用于 WorkBuddy 的 mcd-mcp 连接器等场景，脚本不需要接触 Token：

1. 依次调用下面这些 Tool：
   - `order-list`、`query-my-account`、`list-nutrition-foods`、`now-time-info`（无参数）
   - `query-order`：对 `order-list` 返回的**每一个** `orderId` 各调用一次，参数 `{"orderId": "..."}`
   - `query-my-prizes`：参数 `{"pageNum": "1", "pageSize": "50"}`
   - `query-my-coupons`：参数 `{"page": "1", "pageSize": "200"}`
   - `mall-order-list`：参数 `{"size": 10}`

   只有 `order-list` 是必需的，其余调用失败可以跳过，卡片会少一些内容。
2. 把每个 Tool 的返回结果（`structuredContent` 或其中的 `data` 都可以）以 Tool 名为键，写入 `~/.mcd-persona-card/input.json`。`query-order` 的多次结果放进一个列表：
   ```json
   {
     "order-list": { ... },
     "query-order": [ {...}, {...} ],
     "query-my-account": { ... },
     "query-my-prizes": { ... },
     "query-my-coupons": { ... },
     "mall-order-list": { ... },
     "list-nutrition-foods": { ... },
     "now-time-info": { ... }
   }
   ```
   脚本读取后会自动丢弃门店地址、取餐码、支付单号、备注和金额等字段。
3. 运行：
   ```bash
   python3 <SKILL_DIR>/scripts/run.py card --input ~/.mcd-persona-card/input.json --open
   ```

**方式 C：用户只想先看效果，或没有 Token**

```bash
python3 <SKILL_DIR>/scripts/run.py card --demo --open
```

## 饭搭子匹配

用户发来朋友的分享码（`MC-` 开头）时，**优先用“一个码 + 用户自己的数据”的方式**：

```bash
python3 <SKILL_DIR>/scripts/run.py match <朋友的码> --friend-name 朋友昵称 [数据来源] --open
```

`[数据来源]` 和生成人格卡时保持一致：

| 用户的数据从哪来 | 参数 |
|---|---|
| 方式 A，实时拉取 | 不加 |
| 方式 A，复用上次实时拉取的结果，不再请求接口 | `--cached` |
| 方式 B，连接器取到的文件 | `--input ~/.mcd-persona-card/input.json` |
| 方式 C，演示数据 | `--demo` |

注意：`--cached` 只会读取方式 A 上次实时拉取的缓存，`--demo` 不会写缓存。用户说“就用刚才的演示数据”时，必须用 `--demo`，不要用 `--cached`。

不要传 `--name`，用户这一方会默认显示为“你”，文案最自然。

只有在双方都只有分享码、没有任何数据来源时，才直接比较两个码：

```bash
python3 <SKILL_DIR>/scripts/run.py match <码A> <码B> --name 昵称A --friend-name 昵称B
```

这种方式的匹配度和前一种一样，但叫不出共同本命单品的名字。`--name` 和 `--friend-name` 请填真实昵称，不要填“我”。

## 把结果告诉用户

以下几条对人格卡和匹配结果都适用。

1. 如果用的是演示数据，先明确告诉用户“这是虚构的演示数据”，并说明想看真实结果需要配置 Token（环境变量或 `~/.mcd-persona-card/.env`）或接入 MCP 连接器，但不要让用户把 Token 发到对话里。
2. 用一两句话说出人格类型和名字，例如“你是 早送专省 · 云端早餐家”，并说出积分段位。
3. 介绍“麦门角色”（最多 3 个）和它们的依据，再从“我的麦当劳时间”“场景与口味”“麦门档案”里挑一两条最有意思的。
4. 说明置信度：订单少（置信度“低”）时，提醒用户结果是初步判定；没有订单时，卡片是“待解锁”状态，不会生成饭搭子码。
5. 命令输出里有积分即将过期、券今天到期的提示时，一定要转告用户。
6. 给出饭搭子码，告诉用户可以发给朋友；再告诉用户卡片文件的路径（命令输出的最后一行），页面上可以下载 PNG 图片。
7. 不要编造命令输出里没有的结论。
