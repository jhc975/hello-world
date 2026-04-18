#!/usr/bin/env python3
"""
每日注意力规划系统
Daily Attention Planning System

注意力（前额叶功能）是有限资源。有些活动消耗它，有些活动恢复它。
本系统帮助你规划每天的活动，避免认知透支。

用法:
  python attention.py status          # 查看今日状态
  python attention.py new-day         # 开始新的一天
  python attention.py list            # 列出所有活动
  python attention.py add <id> <min>  # 添加活动到计划
  python attention.py done <index>    # 标记活动已完成
  python attention.py suggest         # 获取当前建议
  python attention.py history         # 查看历史记录
"""

import json
import sys
import argparse
from datetime import date, datetime
from pathlib import Path
from copy import deepcopy

# ─── 配置 ──────────────────────────────────────────────────────────────────────

MAX_ATTENTION = 100
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ACTIVITIES_FILE = BASE_DIR / "activities.json"

# (最低分, 区间名, 建议)
ZONES = [
    (80, "巅峰 PEAK",     "最佳时机：深度工作 / 重要决策 / 创造性思维"),
    (60, "良好 GOOD",     "适合：常规工作 / 学习 / 一般会议"),
    (40, "偏低 LOW",      "仅适合：简单任务 / 整理 / 轻度阅读"),
    (20, "警告 WARNING",  "⚠  停止消耗性任务！立即安排休息"),
    ( 0, "危机 CRITICAL", "🚨 强制休息！避免做任何重要决定"),
]


# ─── 辅助函数 ──────────────────────────────────────────────────────────────────

def get_zone(att: float) -> tuple:
    att = max(0.0, min(100.0, att))
    for lo, label, advice in ZONES:
        if att >= lo:
            return lo, label, advice
    return 0, "危机 CRITICAL", "强制休息"


def attention_bar(att: float, width: int = 28) -> str:
    att = max(0.0, min(100.0, att))
    lo, _, _ = get_zone(att)
    ch = {80: "█", 60: "▓", 40: "▒", 20: "░", 0: " "}.get(lo, "█")
    filled = round(att / 100 * width)
    return "[" + ch * filled + "·" * (width - filled) + f"] {att:5.1f}/100"


def load_activities() -> dict:
    if not ACTIVITIES_FILE.exists():
        print(f"错误：找不到 {ACTIVITIES_FILE}，请确保 activities.json 在同目录。")
        sys.exit(1)
    with open(ACTIVITIES_FILE, encoding="utf-8") as f:
        return json.load(f)


def today_file() -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"{date.today().isoformat()}.json"


def load_today() -> dict | None:
    f = today_file()
    if not f.exists():
        return None
    with open(f, encoding="utf-8") as fp:
        return json.load(fp)


def save_today(data: dict):
    with open(today_file(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_attention(day: dict) -> float:
    """从计划条目重新计算当前注意力。"""
    att = float(day["starting_attention"])
    for e in day["entries"]:
        att = max(0.0, min(MAX_ATTENTION, att + e["delta"]))
    return att


def compute_attention_timeline(day: dict) -> list[float]:
    """返回每条条目执行后的注意力快照列表（含起点）。"""
    att = float(day["starting_attention"])
    timeline = [att]
    for e in day["entries"]:
        att = max(0.0, min(MAX_ATTENTION, att + e["delta"]))
        timeline.append(att)
    return timeline


def calc_delta(activity: dict, duration_min: int, kind: str) -> float:
    if kind == "drain":
        return -(activity["cost_per_hour"] * duration_min / 60.0)
    else:
        # restore 活动有固定恢复量（按比例缩放到实际时长）
        base_restore = activity["restore"]
        base_dur = activity["duration_min"]
        return base_restore * (duration_min / base_dur)


def find_activity(activities: dict, act_id: str) -> tuple[str, dict] | tuple[None, None]:
    for kind in ("drain", "restore"):
        for a in activities[kind]:
            if a["id"] == act_id:
                return kind, a
    return None, None


# ─── 命令：new-day ──────────────────────────────────────────────────────────────

def cmd_new_day(args):
    sleep_quality = args.sleep_quality.lower() if hasattr(args, "sleep_quality") and args.sleep_quality else "normal"
    start_map = {"great": 90, "good": 90, "normal": 75, "poor": 55, "bad": 40}
    starting = start_map.get(sleep_quality, 75)

    existing = load_today()
    if existing:
        print(f"今天（{date.today()}）已有记录。使用 'status' 查看，或手动删除 data/{date.today()}.json 重置。")
        return

    day = {
        "date": date.today().isoformat(),
        "sleep_quality": sleep_quality,
        "starting_attention": starting,
        "entries": [],
        "created_at": datetime.now().isoformat()
    }
    save_today(day)

    print(f"\n✅ 新的一天开始！")
    print(f"   睡眠质量：{sleep_quality}  →  起始注意力：{starting}/100")
    lo, label, advice = get_zone(starting)
    print(f"   当前状态：{label}")
    print(f"   {advice}")
    print(f"\n   使用 'python attention.py add <活动ID> <分钟>' 添加计划。")
    print(f"   使用 'python attention.py list' 查看所有活动。")


# ─── 命令：list ────────────────────────────────────────────────────────────────

def cmd_list(args):
    activities = load_activities()
    print("\n" + "═" * 62)
    print("  消耗型活动（Drain）—— 花费注意力")
    print("═" * 62)
    print(f"  {'ID':<18} {'名称':<22} {'消耗/小时'}")
    print("─" * 62)
    for a in activities["drain"]:
        print(f"  {a['id']:<18} {a['name']:<22} -{a['cost_per_hour']:.0f} pts/h")

    print("\n" + "═" * 62)
    print("  恢复型活动（Restore）—— 补充注意力")
    print("═" * 62)
    print(f"  {'ID':<18} {'名称':<22} {'恢复量':<10} {'参考时长'}")
    print("─" * 62)
    for a in activities["restore"]:
        print(f"  {a['id']:<18} {a['name']:<22} +{a['restore']:<9.0f} {a['duration_min']} min")
    print()


# ─── 命令：add ─────────────────────────────────────────────────────────────────

def cmd_add(args):
    day = load_today()
    if day is None:
        print("今天还没有记录。先运行：python attention.py new-day")
        return

    activities = load_activities()
    kind, act = find_activity(activities, args.id)
    if act is None:
        print(f"找不到活动 ID：{args.id}。使用 'list' 查看所有活动。")
        return

    duration_min = args.minutes
    delta = calc_delta(act, duration_min, kind)

    current = compute_attention(day)
    after = max(0.0, min(MAX_ATTENTION, current + delta))

    # 警告：注意力不足以开始此任务
    if kind == "drain" and current < act.get("min_attention", 0):
        print(f"\n⚠  警告：当前注意力 {current:.0f} 低于此任务推荐最低值 {act['min_attention']}。")
        print("   建议先安排恢复活动。")

    entry = {
        "index": len(day["entries"]),
        "activity_id": args.id,
        "activity_name": act["name"],
        "kind": kind,
        "duration_min": duration_min,
        "delta": round(delta, 1),
        "done": False,
        "added_at": datetime.now().isoformat()
    }
    day["entries"].append(entry)
    save_today(day)

    sign = "+" if delta > 0 else ""
    print(f"\n✅ 已添加：{act['name']}  ({duration_min} min)  {sign}{delta:.1f} pts")
    print(f"   注意力预测：{current:.0f} → {after:.0f}  {attention_bar(after)}")

    # 透支预警
    if after < 20:
        print(f"\n   ⚠  添加后注意力将进入警告区！建议在此之前安排恢复活动。")


# ─── 命令：done ────────────────────────────────────────────────────────────────

def cmd_done(args):
    day = load_today()
    if day is None:
        print("今天还没有记录。先运行：python attention.py new-day")
        return

    idx = args.index
    if idx < 0 or idx >= len(day["entries"]):
        print(f"无效索引 {idx}。今天共有 {len(day['entries'])} 条计划（索引 0~{len(day['entries'])-1}）。")
        return

    entry = day["entries"][idx]
    if entry["done"]:
        print(f"条目 {idx}「{entry['activity_name']}」已经标记完成。")
        return

    entry["done"] = True
    entry["done_at"] = datetime.now().isoformat()
    save_today(day)

    # 计算完成此条目后的注意力
    att = float(day["starting_attention"])
    for e in day["entries"]:
        if e["done"]:
            att = max(0.0, min(MAX_ATTENTION, att + e["delta"]))

    sign = "+" if entry["delta"] > 0 else ""
    print(f"\n✅ 已完成：{entry['activity_name']}  {sign}{entry['delta']:.1f} pts")
    print(f"   当前注意力：{attention_bar(att)}")
    _, label, advice = get_zone(att)
    print(f"   状态：{label}")
    print(f"   {advice}")


# ─── 命令：status ──────────────────────────────────────────────────────────────

def cmd_status(args):
    day = load_today()
    if day is None:
        print("\n今天还没有记录。运行：python attention.py new-day [--sleep-quality great/normal/poor]")
        return

    activities = load_activities()
    timeline = compute_attention_timeline(day)
    current_done_att = float(day["starting_attention"])
    for e in day["entries"]:
        if e["done"]:
            current_done_att = max(0.0, min(MAX_ATTENTION, current_done_att + e["delta"]))

    planned_end = timeline[-1]
    lo, label, advice = get_zone(current_done_att)

    print("\n" + "═" * 62)
    print(f"  📅 {day['date']}  注意力规划状态")
    print("═" * 62)
    print(f"  起始注意力：{day['starting_attention']:.0f}  (睡眠质量：{day['sleep_quality']})")
    print(f"  当前注意力：{attention_bar(current_done_att)}")
    print(f"  状态区间  ：{label}")
    print(f"  建议      ：{advice}")
    if day["entries"]:
        print(f"  计划结束  ：{planned_end:.0f}/100  {attention_bar(planned_end)}")

    print("\n" + "─" * 62)
    print("  活动计划 Timeline")
    print("─" * 62)

    if not day["entries"]:
        print("  （暂无计划，使用 'add' 添加活动）")
    else:
        att = float(day["starting_attention"])
        for i, e in enumerate(day["entries"]):
            after = max(0.0, min(MAX_ATTENTION, att + e["delta"]))
            done_mark = "✓" if e["done"] else "○"
            kind_mark = "▼" if e["kind"] == "drain" else "▲"
            sign = "+" if e["delta"] > 0 else ""
            bar_before = int(att / 100 * 20)
            bar_after = int(after / 100 * 20)
            bar_lo = min(bar_before, bar_after)
            bar_hi = max(bar_before, bar_after)
            bar = " " * bar_lo + ("░" * (bar_hi - bar_lo)) + " " * (20 - bar_hi)
            warn = "  ⚠" if after < 20 and e["kind"] == "drain" else ""
            print(f"  [{done_mark}] {i:2d}. {kind_mark} {e['activity_name']:<22} {e['duration_min']:>3}min  {sign}{e['delta']:>5.1f}  →{after:5.1f}{warn}")
            att = after

    # 透支风险分析
    min_att = min(timeline)
    if min_att < 20:
        overdraft_idx = next(i for i, v in enumerate(timeline) if v < 20)
        entry_name = day["entries"][overdraft_idx - 1]["activity_name"] if overdraft_idx > 0 else "起始"
        print(f"\n  ⚠  透支风险：计划中注意力最低将达 {min_att:.0f}，")
        print(f"     在「{entry_name}」之后进入警告区。")
        print(f"     建议：在该活动前安排恢复活动。")
    elif min_att < 40:
        print(f"\n  ℹ  注意力最低将达 {min_att:.0f}（偏低区），建议穿插休息。")

    print()


# ─── 命令：suggest ─────────────────────────────────────────────────────────────

def cmd_suggest(args):
    day = load_today()
    activities = load_activities()

    if day is None:
        att = 75.0
        print("\n（未找到今日记录，以默认注意力 75 计算建议）")
    else:
        att = float(day["starting_attention"])
        for e in day["entries"]:
            if e["done"]:
                att = max(0.0, min(MAX_ATTENTION, att + e["delta"]))

    lo, label, advice = get_zone(att)
    print(f"\n当前注意力：{attention_bar(att)}  [{label}]")
    print(f"建议：{advice}\n")

    if att >= 60:
        print("── 适合现在做的工作 ──────────────────────────────────")
        suitable = [a for a in activities["drain"] if att >= a.get("min_attention", 0)]
        for a in suitable[:5]:
            drain_1h = a["cost_per_hour"]
            after_1h = max(0, att - drain_1h)
            print(f"  • {a['name']:<24}  消耗约 {drain_1h} pts/h  →  1h后剩余 {after_1h:.0f}")
    else:
        print("── 注意力偏低，不建议做消耗性工作 ───────────────────")
        print("  建议先完成恢复活动，再开始重要任务。\n")

    print("\n── 推荐恢复活动 ───────────────────────────────────────")
    # 按恢复效率（恢复量/分钟）排序
    restore_sorted = sorted(activities["restore"], key=lambda a: a["restore"] / a["duration_min"], reverse=True)
    for a in restore_sorted[:6]:
        after = min(MAX_ATTENTION, att + a["restore"])
        print(f"  • {a['name']:<24}  +{a['restore']:>2} pts  ({a['duration_min']} min)  →  {after:.0f}")

    # 距离下一区间还需多少恢复
    next_zone_targets = [(80, "巅峰"), (60, "良好"), (40, "偏低")]
    needed = None
    for target, name in next_zone_targets:
        if att < target:
            needed = target - att
            print(f"\n  距离【{name}】区间还需恢复 {needed:.0f} pts。")
            break
    print()


# ─── 命令：history ─────────────────────────────────────────────────────────────

def cmd_history(args):
    DATA_DIR.mkdir(exist_ok=True)
    files = sorted(DATA_DIR.glob("*.json"), reverse=True)[:7]
    if not files:
        print("暂无历史记录。")
        return

    print("\n" + "═" * 62)
    print("  历史记录（最近 7 天）")
    print("═" * 62)
    print(f"  {'日期':<12} {'起始':>6} {'结束':>6} {'活动数':>6}  最低点  状态")
    print("─" * 62)
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
        timeline = compute_attention_timeline(d)
        end_att = timeline[-1]
        min_att = min(timeline)
        n = len(d["entries"])
        _, label, _ = get_zone(end_att)
        label_short = label.split()[0]
        print(f"  {d['date']:<12} {d['starting_attention']:>6.0f} {end_att:>6.1f} {n:>6}    {min_att:>4.0f}   {label_short}")
    print()


# ─── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="每日注意力规划系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python attention.py new-day --sleep-quality great
  python attention.py list
  python attention.py add deep_work 90
  python attention.py add nap 25
  python attention.py status
  python attention.py done 0
  python attention.py suggest
  python attention.py history
        """
    )
    sub = parser.add_subparsers(dest="cmd")

    # new-day
    p_new = sub.add_parser("new-day", help="开始新的一天")
    p_new.add_argument("--sleep-quality", dest="sleep_quality",
                       choices=["great", "good", "normal", "poor", "bad"],
                       default="normal",
                       help="睡眠质量（影响起始注意力）")

    # list
    sub.add_parser("list", help="列出所有可用活动")

    # add
    p_add = sub.add_parser("add", help="添加活动到今日计划")
    p_add.add_argument("id", help="活动 ID（使用 list 命令查看）")
    p_add.add_argument("minutes", type=int, help="时长（分钟）")

    # done
    p_done = sub.add_parser("done", help="标记某活动已完成")
    p_done.add_argument("index", type=int, help="活动序号（见 status 输出）")

    # status
    sub.add_parser("status", help="查看今日注意力状态和计划")

    # suggest
    sub.add_parser("suggest", help="根据当前注意力获取建议")

    # history
    sub.add_parser("history", help="查看最近 7 天历史")

    args = parser.parse_args()

    dispatch = {
        "new-day":  cmd_new_day,
        "list":     cmd_list,
        "add":      cmd_add,
        "done":     cmd_done,
        "status":   cmd_status,
        "suggest":  cmd_suggest,
        "history":  cmd_history,
    }

    if args.cmd is None:
        parser.print_help()
        return

    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
