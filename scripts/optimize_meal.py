#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦点餐最优解 · 组合优化引擎 (mcd-meal-optimizer)

设计原则
--------
本脚本是「纯本地计算引擎」：
  * 不联网、不发起任何 HTTP 请求
  * 不读取、不存储、不打印任何麦当劳凭证 (MCP Token)
  * 只吃一份 JSON（菜单 / 价格 / 优惠券 / 营养 / 用户约束），吐一份 JSON + Markdown

那份输入 JSON 由 WorkBuddy 通过麦当劳 MCP 拉取后落盘传入。
这样拆分的好处：
  1. 组合枚举是纯数学问题，交给脚本比交给大模型更快、更准、更省积分；
  2. 大模型只负责「理解需求」和「组织话术」，不碰金额计算，避免算错价；
  3. 凭证永远留在 MCP Client 里，脚本这一层没有泄密面。

用法
----
    python scripts/optimize_meal.py --input scripts/demo_input.json
    python scripts/optimize_meal.py --demo
    python scripts/optimize_meal.py --input in.json --out result.json --top 3
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations

# --------------------------------------------------------------------------
# 1. 品类归一化
# --------------------------------------------------------------------------
# 麦当劳 MCP 的 query-meals 返回的 category 文案可能随门店/版本变化，
# 所以这里做一层「关键词兜底」：先认 category，认不出来再认餐品名。
CATEGORY_RULES = [
    ("主食", ("汉堡", "堡", "卷", "饭", "麦满分", "粥", "卷饼")),
    ("甜品", ("冰淇淋", "新地", "圣代", "派", "麦旋风", "蛋糕", "甜筒", "布丁", "麦咖啡甜")),
    ("饮品", ("可乐", "咖啡", "茶", "奶", "汁", "水", "雪碧", "豆浆", "拿铁", "美式", "特饮", "冰沙", "气泡")),
    ("配餐", ("薯条", "薯饼", "鸡块", "鸡翅", "沙拉", "玉米", "苹果", "麦乐鸡", "鸡排", "鸡条", "洋葱", "鸡腿")),
]

ALL_CATEGORIES = ["主食", "配餐", "饮品", "甜品", "其他"]


def normalize_category(item: dict) -> str:
    """把一个餐品归到 主食/配餐/饮品/甜品/其他 五类之一。"""
    raw = str(item.get("category") or "").strip()
    for name, _ in CATEGORY_RULES:
        if name and name in raw:
            return name
    blob = f"{item.get('name', '')} {raw}"
    for name, keys in CATEGORY_RULES:
        if any(k in blob for k in keys):
            return name
    return "其他"


# --------------------------------------------------------------------------
# 2. 优惠券折算
# --------------------------------------------------------------------------
def coupon_discount(coupon: dict, items: list[dict], subtotal: float) -> float:
    """算出这张券在这个组合上能减多少钱（不能减就返回 0）。"""
    ctype = str(coupon.get("type") or "").strip().lower()
    cats = coupon.get("applicable_categories") or []
    if cats:
        base = sum(float(i.get("price") or 0) for i in items if normalize_category(i) in cats)
    else:
        base = subtotal
    if base <= 0:
        return 0.0

    # 满减：满 threshold 减 discount
    if ctype in ("full_reduction", "满减", "threshold"):
        threshold = float(coupon.get("threshold") or 0)
        if subtotal < threshold:
            return 0.0
        return min(float(coupon.get("discount") or 0), subtotal)

    # 折扣：rate=0.88 表示打 88 折
    if ctype in ("discount", "折扣", "rate"):
        rate = float(coupon.get("rate") or 1)
        if rate >= 1:
            return 0.0
        return round(base * (1 - rate), 2)

    # 直减 / 代金券
    if ctype in ("fixed", "cash", "直减", "代金券"):
        return min(float(coupon.get("discount") or 0), subtotal)

    return 0.0


def best_coupon(coupons: list[dict], items: list[dict], subtotal: float) -> tuple[float, str | None]:
    """从所有可用券里挑最省的一张（麦当劳一张订单通常只能用一张券）。"""
    best, best_name = 0.0, None
    for c in coupons:
        d = coupon_discount(c, items, subtotal)
        if d > best:
            best, best_name = d, c.get("name") or c.get("couponId") or "优惠券"
    return round(best, 2), best_name


# --------------------------------------------------------------------------
# 3. 组合枚举
# --------------------------------------------------------------------------
def build_pools(menu: list[dict], constraints: dict) -> dict[str, list[dict]]:
    pools: dict[str, list[dict]] = {c: [] for c in ALL_CATEGORIES}
    exclude = [x for x in (constraints.get("exclude") or []) if x]
    for it in menu:
        blob = f"{it.get('name', '')} {it.get('category', '')} {' '.join(it.get('tags') or [])}"
        if any(x in blob for x in exclude):
            continue
        pools[normalize_category(it)].append(it)
    return pools


def plan_key(items: list[dict]) -> tuple:
    return tuple(sorted(str(i.get("code") or i.get("name")) for i in items))


def summarize(items: list[dict], coupons: list[dict]) -> dict:
    subtotal = round(sum(float(i.get("price") or 0) for i in items), 2)
    discount, coupon_name = best_coupon(coupons, items, subtotal)
    nutrition = {
        "calories": round(sum(float(i.get("calories") or 0) for i in items), 1),
        "protein": round(sum(float(i.get("protein") or 0) for i in items), 1),
        "fat": round(sum(float(i.get("fat") or 0) for i in items), 1),
        "carbs": round(sum(float(i.get("carbs") or 0) for i in items), 1),
        "sodium": round(sum(float(i.get("sodium") or 0) for i in items), 1),
    }
    return {
        "items": [
            {
                "code": i.get("code"),
                "name": i.get("name"),
                "category": normalize_category(i),
                "price": round(float(i.get("price") or 0), 2),
                "calories": float(i.get("calories") or 0),
                "protein": float(i.get("protein") or 0),
            }
            for i in items
        ],
        "subtotal": subtotal,
        "discount": discount,
        "coupon": coupon_name,
        "payable": round(subtotal - discount, 2),
        "nutrition": nutrition,
    }


def enumerate_plans(menu: list[dict], coupons: list[dict], constraints: dict,
                    limit: int = 40000) -> list[dict]:
    pools = build_pools(menu, constraints)
    staples = pools["主食"] or pools["其他"] or menu
    sides = pools["配餐"] + pools["其他"]
    drinks = pools["饮品"]
    desserts = pools["甜品"]

    must = [m for m in (constraints.get("must_include") or []) if m]
    max_cal = constraints.get("max_calories")
    min_protein = constraints.get("min_protein")
    max_payable = constraints.get("max_payable")

    plans, seen = [], set()
    n = 0
    for staple_count in (1, 2):
        for staple_combo in combinations(staples, staple_count):
            if n > limit:
                break
            for side in [None] + sides[:40]:
                for drink in [None] + drinks[:40]:
                    for dessert in [None] + desserts[:30]:
                        items = list(staple_combo)
                        for extra in (side, drink, dessert):
                            if extra is not None and extra not in items:
                                items.append(extra)
                        n += 1
                        k = plan_key(items)
                        if k in seen:
                            continue
                        seen.add(k)

                        blob = " ".join(str(i.get("name") or "") for i in items)
                        if must and not all(m in blob for m in must):
                            continue

                        plan = summarize(items, coupons)
                        nut = plan["nutrition"]
                        if max_cal is not None and nut["calories"] > float(max_cal):
                            continue
                        if min_protein is not None and nut["protein"] < float(min_protein):
                            continue
                        if max_payable is not None and plan["payable"] > float(max_payable):
                            continue
                        plans.append(plan)
    return plans


# --------------------------------------------------------------------------
# 4. 三种「口味」的推荐
# --------------------------------------------------------------------------
def pick_recommendations(plans: list[dict], constraints: dict, top: int = 3) -> dict:
    if not plans:
        return {"cheapest": [], "healthiest": [], "best_value": []}

    target_cal = float(constraints.get("target_calories") or 0) or None
    target_protein = float(constraints.get("target_protein") or 0) or None

    def health_score(p: dict) -> float:
        """越接近目标热量/蛋白越好；没设目标就按「低脂高蛋白」排。"""
        nut = p["nutrition"]
        if target_cal:
            cal_pen = abs(nut["calories"] - target_cal) / target_cal
        else:
            cal_pen = nut["fat"] / 100.0
        if target_protein:
            pro_pen = max(0.0, target_protein - nut["protein"]) / target_protein
        else:
            pro_pen = max(0.0, 25 - nut["protein"]) / 25.0
        return round(cal_pen + pro_pen, 4)

    cheapest = sorted(plans, key=lambda p: (p["payable"], -p["nutrition"]["protein"]))
    healthiest = sorted(plans, key=lambda p: (health_score(p), p["payable"]))
    # 性价比：每花 1 块钱能换到多少蛋白质，且热量不能超标
    best_value = sorted(
        plans,
        key=lambda p: (-(p["nutrition"]["protein"] / max(p["payable"], 1e-6)), p["payable"]),
    )

    def dedupe(seq, k):
        out, keys = [], set()
        for p in seq:
            kk = plan_key([{"code": i["code"], "name": i["name"]} for i in p["items"]])
            if kk in keys:
                continue
            keys.add(kk)
            out.append(p)
            if len(out) >= k:
                break
        return out

    return {
        "cheapest": dedupe(cheapest, top),
        "healthiest": dedupe(healthiest, top),
        "best_value": dedupe(best_value, top),
    }


# --------------------------------------------------------------------------
# 5. 渲染
# --------------------------------------------------------------------------
def render_markdown(result: dict) -> str:
    c = result["constraints"]
    lines = ["# 麦麦点餐最优解", ""]
    lines.append(
        f"> 约束：预算 ≤ ¥{c.get('max_payable', '不限')}｜"
        f"热量 ≤ {c.get('max_calories', '不限')} kcal｜"
        f"蛋白质 ≥ {c.get('min_protein', '不限')} g"
    )
    lines.append("")
    lines.append(f"共枚举出 **{result['stats']['total_plans']}** 套满足约束的组合。")
    lines.append("")

    titles = {
        "cheapest": "① 最省方案",
        "healthiest": "② 最健康方案",
        "best_value": "③ 性价比之王",
    }
    for key, title in titles.items():
        plans = result["recommendations"].get(key) or []
        if not plans:
            continue
        lines.append(f"## {title}")
        lines.append("")
        for idx, p in enumerate(plans, 1):
            nut = p["nutrition"]
            lines.append(f"**{idx}. 实付 ¥{p['payable']}**（原价 ¥{p['subtotal']}"
                         + (f"，用券「{p['coupon']}」省 ¥{p['discount']}" if p["discount"] else "，无可用券")
                         + f"）｜{nut['calories']:.0f} kcal｜蛋白 {nut['protein']:.0f} g")
            for i in p["items"]:
                lines.append(f"- {i['category']}：{i['name']}　¥{i['price']}")
            lines.append("")
    if not any(result["recommendations"].values()):
        lines.append("⚠️ 没有组合能满足当前约束，建议放宽预算或热量上限。")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 6. 入口
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="麦麦点餐最优解 · 组合优化引擎")
    ap.add_argument("--input", help="输入 JSON 路径（菜单/券/约束）")
    ap.add_argument("--out", help="输出 JSON 路径（不填则打印到 stdout）")
    ap.add_argument("--md", help="输出 Markdown 路径")
    ap.add_argument("--top", type=int, default=3, help="每类推荐几套，默认 3")
    ap.add_argument("--demo", action="store_true", help="用内置示例数据跑一遍")
    args = ap.parse_args(argv)

    if args.demo or not args.input:
        import os
        demo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_input.json")
        if not os.path.exists(demo):
            print("找不到 demo_input.json，请用 --input 指定输入文件", file=sys.stderr)
            return 2
        with open(demo, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)

    menu = payload.get("menu") or []
    coupons = payload.get("coupons") or []
    constraints = payload.get("constraints") or {}

    if not menu:
        print("输入里没有 menu，没法算。", file=sys.stderr)
        return 2

    plans = enumerate_plans(menu, coupons, constraints)
    result = {
        "constraints": constraints,
        "stats": {
            "menu_size": len(menu),
            "coupon_size": len(coupons),
            "total_plans": len(plans),
        },
        "recommendations": pick_recommendations(plans, constraints, args.top),
    }

    md = render_markdown(result)
    result["markdown"] = md

    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    if not args.out and not args.md:
        print(md)
    else:
        print(md if args.md else json.dumps(result["stats"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
