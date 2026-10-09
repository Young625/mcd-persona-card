# 麦当劳 MCP 接入说明

## 1. 使用的 MCP Server

| 项目 | 内容 |
|---|---|
| 服务 | 麦当劳中国 MCP Server（[open.mcd.cn/mcp](https://open.mcd.cn/mcp)） |
| 地址 | `https://mcp.mcd.cn` |
| 协议 | MCP Streamable HTTP（JSON-RPC 2.0），协议版本 `2025-03-26` |
| 鉴权 | 请求头 `Authorization: Bearer <MCD_MCP_TOKEN>`，Token 只从环境变量或 `.env` 文件读取 |
| 客户端实现 | [`mcp_client.py`](scripts/mcd_persona/mcp_client.py)，只用 Python 标准库，兼容 `application/json` 和 `text/event-stream` 两种响应 |

支持两种接入方式：

- **脚本直连**：`run.py` 自己通过上面的客户端调用 MCP。
- **Agent 连接器**：Agent（例如 WorkBuddy 的 mcd-mcp 连接器）调用 MCP，把结果写成文件交给脚本，脚本完全不接触 Token。具体步骤见 [`SKILL.md`](SKILL.md) 的方式 B。

## 2. 实际调用的 Tool（共 8 个，全部只读）

| Tool | 用途 | 用到的字段 |
|---|---|---|
| `order-list` | 最近的订单（实测最多返回 10 单）。人格的主要数据来源 | `createTime`、`orderType`、`beType`、`orderStatus`、`storeCode`、`orderProductList[].comboItemList[]` |
| `query-order` | 逐单查询详情，得到取餐方式和用券情况 | `takeWay`、`couponList` 的张数、`totalDiscountAmount ÷ totalAmount`（只保留比例） |
| `query-my-account` | 积分账户，用于积分段位和积分利用率 | `accumulativePoint`、`usedPoint`、`expiredPoint`、`currentMouthExpirePoint` |
| `query-my-prizes` | 奖品记录，统计节气门票和其他奖品（每页 50 条，最多 3 页） | `name`、`prizeTypeText` |
| `query-my-coupons` | 券包，用于提醒今天到期的券 | 券的数量、`tags` 中的“今日到期” |
| `mall-order-list` | 积分商城兑换记录（近一年，最多 5 页） | 订单数量 |
| `list-nutrition-foods` | 餐品营养成分，用于估算平均每单热量和蛋白质 | `productName`、`energyKcal`、`protein` |
| `now-time-info` | 服务器时间，用于计算下单频率 | `formatted` |

**不调用的 Tool**：`create-order`、`cancel-order`、`auto-bind-coupons`、`draw-lottery`、`mall-create-order`、`party-order-create`、`delivery-create-address` 等所有会改变账户状态的工具。本项目对账户只读，不会下单、领券、抽奖或扣积分。

## 3. 调用流程

```
initialize ──► notifications/initialized
    │
    ├─► now-time-info / order-list / query-my-account / list-nutrition-foods
    ├─► query-order × N（order-list 里的每一单）
    ├─► query-my-prizes（分页）/ query-my-coupons / mall-order-list（分页）
    │         除 order-list 外，任何一个调用失败都只跳过对应模块，不中断
    ▼
collect.py   采集时立即精简：丢弃门店名称、地址、取餐码、支付单号、备注和金额
    │        精简结果缓存到 ~/.mcd-persona-card/cache/raw.json（权限 600）
    ▼
features.py  计算统计指标（全部在本地进行）
    ▼
persona.py   四维主人格 + 麦门角色 + 积分段位
    │
    ├──► render.py      人格卡（SVG / HTML / PNG）
    └──► share_code.py  饭搭子码 ──► match.py 和朋友的码比较 ──► 匹配卡
```

每次运行一共调用约 10～20 次接口，远低于每分钟 600 次的限流。

## 4. 数据如何变成人格

### 4.1 四维主人格（16 种）

| 维度 | 计算方式 | 数据来源 |
|---|---|---|
| 早餐派 / 正餐派 | 10:30 前下单的订单占比 ≥ 50% 判为早餐派 | `order-list.createTime` |
| 外送派 / 到店派 | 外送订单（`orderType=2`）占比 ≥ 50% 判为外送派 | `order-list.orderType` |
| 专一派 / 尝鲜派 | 出现"在其他订单里也点过的餐品"的订单占比 ≥ 50% 判为专一派（不算饮品） | `order-list.orderProductList` |
| 精打细算 / 随性派 | 用券订单占比 × 60% + 积分利用率 × 40% ≥ 50% 判为精打细算；缺少哪项就只用另一项 | `query-order.couponList`、`query-my-account` |

### 4.2 麦门角色（18 种，最多展示 3 个）

按顺序检查规则，取前 3 个命中的。每个角色都附带依据：

| 角色 | 规则 | 角色 | 规则 |
|---|---|---|---|
| 节气收集家 | 节气门票 ≥ 12 枚 | 甜品鉴赏家 | ≥ 40% 的订单有甜品 |
| 早八元气派 | ≥ 50% 的订单是工作日早餐 | 无糖主义 | ≥ 50% 的饮品是无糖款 |
| 周末犒劳派 | ≥ 60% 的订单在周末 | 蛋白质搭子 | 平均每单蛋白质 ≥ 30 克 |
| 券包管理大师 | ≥ 60% 的订单用了券 | 一店到底 | ≥ 5 单都在同一家店 |
| 分享担当 | ≥ 40% 的订单一次点 3 份以上主食 | 门店收集家 | 去过 ≥ 4 家门店 |
| 堂食仪式感 | ≥ 50% 的订单是堂食 | 积分玩家 | 积分兑换或抽中奖品 ≥ 3 次 |
| 得来速车手 | ≥ 30% 的订单走得来速 | 麦门常驻 | 平均每月 ≥ 6 单 |
| 团餐组织者 | 有企业团餐订单 | 尝鲜先锋 | 吃过 ≥ 10 种餐品 |
| 咖啡搭子 | ≥ 40% 的订单有咖啡 | 一人食达人 | ≥ 80% 的订单只有 1 份主食 |

角色文案只描述事实，不鼓励过量或不健康的饮食。

### 4.3 其他模块

| 模块 | 内容 | 数据来源 |
|---|---|---|
| 积分段位 | 按累计积分分为萌新、常客（300）、资深（1000）、元老（3000）、传奇（8000），并显示距离下一段位还差多少分 | `query-my-account` |
| 我的麦当劳时间 | 最常出没的星期和时段（并列时如实显示）、5 个时段的分布、工作日和周末的占比、平均每月单数 | `order-list.createTime`、`now-time-info` |
| 场景与口味 | 堂食、外带、外送、得来速、团餐的分布；主食、小食、甜品、饮品的份数占比 | `query-order.takeWay`、`order-list.beType`、`orderProductList` |
| 麦门档案 | 本命单品和饮品、平均每单热量和蛋白质、用券订单占比和平均优惠比例、节气门票、门店数量 | 多个 Tool |

### 4.4 按数据量分档

| 订单数 | 置信度 | 处理方式 |
|---|---|---|
| 6～10 单 | 高 | 完整卡片 |
| 3～5 单 | 中 | 完整卡片 |
| 1～2 单 | 低 | 标注"初步判定"；订单少于 2 单时"专一/尝鲜"显示数据不足 |
| 0 单 | 待解锁 | 生成"麦门新朋友"卡，只展示积分段位、节气门票、券包和兑换次数，不生成饭搭子码 |

另外两点：

- 套餐会按 `comboItemList` 拆成单品后再统计；已取消、已退款的订单不参与计算。
- 营养数据只统计能和营养表对上的餐品，覆盖率低于 60% 时不展示。

## 5. 隐私设计

| 数据 | 采集后 | 终端输出 | 人格卡 | 分享码 |
|---|---|---|---|---|
| 人格、角色、各项占比 | 计算得出 | ✅ | ✅ | 只存四维得分和品类占比 |
| 本命单品、饮品 | 保留 | ✅ | ✅ | 只存餐品编码 |
| 门店 | 只保留编码，用来计数 | 只显示数量 | 只显示数量 | ❌ |
| 金额 | 只保留优惠比例，原始金额立即丢弃 | 只显示比例 | 只显示比例 | ❌ |
| 门店地址、取餐码、支付单号、订单备注 | 立即丢弃 | ❌ | ❌ | ❌ |
| 订单号、账户 ID、Token | 不输出 | ❌ | ❌ | ❌ |

- Token 只从环境变量 `MCD_MCP_TOKEN` 或 `.env` 文件（推荐 `~/.mcd-persona-card/.env`）读取，从不写进仓库。
- 缓存和卡片保存在 `~/.mcd-persona-card/`，不会写进仓库或用户当前的项目。
- 所有计算都在本地完成，没有服务器，不上传任何数据。
- 分享码可以完整解码（见 [`share_code.py`](scripts/mcd_persona/share_code.py)），里面只有统计结果。

## 6. 业务价值

- **让会员数据变得好玩、可分享**：把订单、积分、节气门票这些分散的数据整合成一张人格卡，用户愿意截图分享。
- **社交裂变**：饭搭子码让一个人的分享自然带出第二个人，匹配结果还会给出"一起点什么"的建议，把分享落到实际的到店或外送场景。
- **会员权益提醒**：提示即将过期的积分和今天到期的券，帮用户少浪费权益。
- **覆盖所有用户**：从 0 单到 10 单都能生成合适的卡片，新用户也有积分段位等内容可看。
- **零门槛**：自带演示数据，没有 Token 也能先体验。
