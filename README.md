# 麦麦点餐最优解 · mcd-meal-optimizer

> 一个跑在 **WorkBuddy** 上的 Skill：接 **麦当劳 MCP** 拉真实菜单、真实营养、真实优惠券，
> 用本地组合优化引擎穷举所有搭配，算出「最省 / 最健康 / 性价比最高」三套**能直接下单**的方案。

---

## 一句话说明它解决什么

**麦当劳的优惠券是满减、折扣、品类限定混着来的，人脑算不过来。**

举个真实的坑：

- 你手里有「满 40 减 10」和「汉堡 8.8 折」。
- 买一个 25.5 元的巨无霸：8.8 折省 3.06 元，满 40 减 10 用不了 → 8.8 折赢。
- 买两个 25.5 元的巨无霸（51 元）：8.8 折省 6.12 元，满 40 减 10 省 10 元 → 满减赢。
- 再加一份 12 元薯条凑到 63 元：**薯条白买了** —— 因为券已经封顶在减 10，多花的 12 元一分没省。

**哪张券最省、要不要凑单，取决于你这单的构成。** 这个 Skill 把这件事算准。

再叠上预算、热量、蛋白质三重约束后，可选组合轻松上千套（示例数据里是 **1554 套**），
人手不可能算完 —— 但脚本几毫秒就跑完了。

---

## 目标用户

- **健身 / 控糖人群**：想点麦当劳，但要卡热量和蛋白质。
- **上班族午休**：预算固定，想在预算内吃到最划算的一餐。
- **多人拼单**：两三个人一起吃，要凑券又不想浪费。
- **纯省钱党**：手里攒了一堆券，想知道哪张该在哪单用。

---

## 它是怎么工作的

```
用户在 WorkBuddy 里说：
「两个人吃，50 块以内，热量别超 1200，蛋白质要够」
        │
        ▼
┌───────────────────────────────────────────────┐
│  WorkBuddy（负责理解需求 + 组织话术）           │
│    ↓ 调用麦当劳 MCP                            │
│  query-meals          拉门店真实菜单            │
│  list-nutrition-foods 拉餐品营养数据            │
│  query-store-coupons  拉门店可用券              │
│  query-my-coupons     拉账户已有券              │
│  calculate-price      对最终方案核价            │
└───────────────────────────────────────────────┘
        │  落盘成一份 JSON
        ▼
┌───────────────────────────────────────────────┐
│  optimize_meal.py（纯本地，不联网）             │
│    1. 品类归一化   → 主食/配餐/饮品/甜品        │
│    2. 组合枚举     → 逐个组合过约束             │
│    3. 券最优匹配   → 挑本单最省的那张           │
│    4. 三种口味排序 → 最省 / 最健康 / 性价比     │
└───────────────────────────────────────────────┘
        │
        ▼
   三套可直接下单的方案
```

**为什么把计算拆出来给脚本？**

| 交给大模型算 | 交给脚本算 |
|---|---|
| 会算错金额 | 精确到分 |
| 枚举不全，凭感觉 | 1554 套全跑 |
| 每轮都烧积分 | 零积分 |
| 结果不稳定 | 同样输入同样输出 |

大模型只干它擅长的事：**听懂"别太油"是什么意思**、**把结果讲成人话**。

---

## 安装

### 1. 申请麦当劳 MCP Token

1. 打开 <https://open.mcd.cn/mcp>，右上角点【登录】，用手机号验证登录
2. 登录后右上角变成【控制台】，点开 → 点【激活】→ 同意服务协议
3. 复制生成的 **MCP Token**（形如 `Bearer` 后面那一串）

> ⚠️ Token 和你的麦当劳会员账号强绑定，**持有即拥有你账号的操作权限**。不要分享、不要提交到 Git。

### 2. 在 WorkBuddy 里配置麦当劳 MCP

复制 `mcp-config.example.json`，把 `${MCD_MCP_TOKEN}` 换成你的真实 Token，粘进 WorkBuddy 的 MCP 配置：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

### 3. 放入 Skill 目录

把整个 `mcd-meal-optimizer/` 目录放到 WorkBuddy 的 Skills 目录下：

- 用户级（所有项目可用）：`~/.workbuddy-ai/skills/mcd-meal-optimizer/`
- 项目级（仅当前项目）：`{工作区}/.workbuddy-ai/skills/mcd-meal-optimizer/`

### 4. 环境要求

- Python 3.9 及以上（**只用标准库**，不需要 `pip install` 任何东西）
- WorkBuddy 客户端（支持 Streamable HTTP 协议的 MCP）

---

## 使用示例

### 示例一：直接跑引擎（不需要 MCP，用内置示例数据）

```bash
python scripts/optimize_meal.py --demo
```

输出：

```
# 麦麦点餐最优解

> 约束：预算 ≤ ¥45｜热量 ≤ 1100 kcal｜蛋白质 ≥ 35 g

共枚举出 **1554** 套满足约束的组合。

## ① 最省方案
**1. 实付 ¥24.0**（原价 ¥30.0，用券「满 30 减 6」省 ¥6.0）｜720 kcal｜蛋白 35 g
- 主食：麦香鸡　¥17.0
- 主食：吉士汉堡　¥13.0
...

## ② 最健康方案
**1. 实付 ¥35.0**（原价 ¥45.0，用券「满 40 减 10」省 ¥10.0）｜810 kcal｜蛋白 45 g
- 主食：板烧鸡腿堡　¥23.5
- 配餐：麦乐鸡 5 块　¥13.5
- 饮品：豆浆　¥8.0
...

## ③ 性价比之王
**1. 实付 ¥32.0**（原价 ¥42.0，用券「满 40 减 10」省 ¥10.0）｜880 kcal｜蛋白 50 g
- 主食：那么大鸡排　¥18.0
- 配餐：麦乐鸡 10 块　¥24.0
```

### 示例二：用真实数据跑

```bash
# WorkBuddy 调完 MCP 后落盘 meal_input.json，然后：
python scripts/optimize_meal.py --input meal_input.json --out meal_result.json --md meal_result.md
```

### 示例三：在 WorkBuddy 里直接说话

```
帮我点麦当劳，两个人吃，预算 50 块以内，
热量加起来别超 1200，蛋白质要 40 克以上，不要牛肉。
```

WorkBuddy 会自动加载本 Skill，拉真实菜单和券，然后给出三套方案。

---

## 输入 JSON 格式

```jsonc
{
  "constraints": {
    "max_payable": 45,        // 实付上限（用券之后）
    "max_calories": 1100,     // 总热量上限 kcal
    "min_protein": 35,        // 总蛋白质下限 g
    "target_calories": 800,   // 目标热量（"最健康"按偏离度排）
    "target_protein": 45,     // 目标蛋白质
    "must_include": [],       // 必须包含的关键词，如 ["咖啡"]
    "exclude": []             // 排除的关键词，如 ["牛肉", "辣"]
  },
  "menu": [
    { "code": "B001", "name": "巨无霸", "category": "汉堡",
      "price": 25.5, "calories": 550, "protein": 25, "fat": 28, "carbs": 45, "sodium": 950 }
  ],
  "coupons": [
    { "couponId": "C-FULL40-10", "name": "满 40 减 10",
      "type": "full_reduction", "threshold": 40, "discount": 10,
      "applicable_categories": [] }   // 空数组 = 全场通用
  ]
}
```

**支持的券类型**

| `type` | 含义 | 需要哪些字段 |
|---|---|---|
| `full_reduction` | 满 X 减 Y | `threshold`、`discount` |
| `discount` | 折扣券 | `rate`（0.88 = 8.8 折） |
| `fixed` | 直减 / 代金券 | `discount` |

`applicable_categories` 填 `["主食"]` / `["配餐"]` / `["饮品"]` / `["甜品"]`，留空表示全场。

---

## 命令行参数

```
--input PATH   输入 JSON 路径
--out PATH     输出结果 JSON 路径
--md PATH      输出 Markdown 路径
--top N        每类推荐几套，默认 3
--demo         用内置示例数据跑一遍
```

---

## 项目文件

| 文件 | 说明 |
|---|---|
| `SKILL.md` | WorkBuddy 技能定义（工作流、边界、红线） |
| `README.md` | 本文件 |
| `MCP_INTEGRATION.md` | 实际调用了哪些麦当劳 MCP 工具、调用流程、业务价值 |
| `mcp-config.example.json` | MCP 配置示例，**只含环境变量占位符，无真实 Token** |
| `workbuddy.md` | 用 WorkBuddy 开发本项目的过程记录 |
| `CONTEST_DECLARATION.md` | 参赛声明（原创性 / 合规性 / 敏感信息） |
| `scripts/optimize_meal.py` | 组合优化引擎，纯本地、无网络、无依赖 |
| `scripts/demo_input.json` | 示例输入数据 |

---

## 边界与合规

- 本 Skill **不主动下单、不自动领券**。涉及花钱或改动账号的操作，一律先向用户确认。
- 严格遵守《[麦当劳 MCP 服务规则](https://cdn.mcd.cn/cms/pages/MCPServerRules.html)》：仅个人非商业用途，不做批量 / 高频自动化调用，不做代下单、代领券、倒卖优惠权益。
- 接口限流：**600 次/分钟**，超出返回 `429`。本项目正常使用远低于该阈值。
- 营养与价格数据**一律以麦当劳 MCP 返回为准**，本项目不内置任何硬编码的营养表。

## License

MIT
