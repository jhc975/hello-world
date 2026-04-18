#!/usr/bin/env python3
"""
Apple Watch 睡眠数据同步
每天上午 10:00 由 launchd 自动运行。

数据流：
  Apple Watch → 健康 App → 捷径自动化写入 JSON → 本脚本读取 → 映射质量等级
  → 调用 attention.py new-day --sleep-quality <等级>

JSON 格式（由捷径写入 ~/.attention_sync/sleep_<日期>.json）：
{
  "date": "2026-04-18",
  "total_sleep_minutes": 450,
  "deep_sleep_minutes": 75,
  "rem_sleep_minutes": 90,
  "awakenings": 2,
  "efficiency": 0.88
}
"""

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SYNC_DIR = Path.home() / ".attention_sync"
SCRIPT_DIR = Path(__file__).parent


# ─── 睡眠质量分类 ──────────────────────────────────────────────────────────────

def classify_sleep(data: dict) -> tuple[str, str]:
    """
    将睡眠指标映射为质量等级。
    返回 (quality_label, human_summary)
    """
    total_min = float(data.get("total_sleep_minutes", 0))
    deep_min  = float(data.get("deep_sleep_minutes", 0))
    rem_min   = float(data.get("rem_sleep_minutes", 0))
    awakenings = int(data.get("awakenings", 0))
    efficiency = float(data.get("efficiency", 0.85))

    total_h  = total_min / 60
    deep_pct = deep_min / total_min if total_min > 0 else 0
    rem_pct  = rem_min  / total_min if total_min > 0 else 0

    score = 0

    # 总睡眠时长（权重 40分）
    if   total_h >= 8.0: score += 40
    elif total_h >= 7.5: score += 35
    elif total_h >= 7.0: score += 28
    elif total_h >= 6.0: score += 18
    elif total_h >= 5.0: score += 8
    else:                score += 0

    # 深度睡眠占比（权重 25分，目标 ≥15%）
    if   deep_pct >= 0.20: score += 25
    elif deep_pct >= 0.15: score += 20
    elif deep_pct >= 0.10: score += 13
    elif deep_pct >= 0.05: score += 6
    else:                  score += 0

    # REM 占比（权重 20分，目标 ≥20%）
    if   rem_pct >= 0.25: score += 20
    elif rem_pct >= 0.20: score += 16
    elif rem_pct >= 0.15: score += 10
    else:                 score += 4

    # 睡眠效率（权重 15分）
    if   efficiency >= 0.90: score += 15
    elif efficiency >= 0.85: score += 12
    elif efficiency >= 0.75: score += 7
    else:                    score += 2

    # 觉醒次数惩罚
    if awakenings >= 4: score -= 8
    elif awakenings >= 2: score -= 3

    score = max(0, min(100, score))

    if   score >= 82: quality = "great"
    elif score >= 64: quality = "good"
    elif score >= 46: quality = "normal"
    elif score >= 30: quality = "poor"
    else:             quality = "bad"

    summary = (
        f"总睡眠 {total_h:.1f}h｜深度 {deep_pct*100:.0f}%｜"
        f"REM {rem_pct*100:.0f}%｜效率 {efficiency*100:.0f}%｜"
        f"质量评分 {score}/100 → {quality}"
    )
    return quality, summary


# ─── 文件读取 ──────────────────────────────────────────────────────────────────

def find_sleep_file(for_date: date) -> Path | None:
    """
    按优先级查找睡眠 JSON：
      1. ~/.attention_sync/sleep_<今天>.json
      2. ~/.attention_sync/sleep_<昨天>.json（早起时 Watch 数据还在昨天）
    """
    for d in (for_date, for_date - timedelta(days=1)):
        path = SYNC_DIR / f"sleep_{d.isoformat()}.json"
        if path.exists():
            return path
    return None


def read_sleep_data(for_date: date) -> dict | None:
    path = find_sleep_file(for_date)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ─── 主流程 ────────────────────────────────────────────────────────────────────

def run_new_day(quality: str, dry_run: bool = False):
    attention_script = SCRIPT_DIR / "attention.py"
    cmd = [sys.executable, str(attention_script), "new-day",
           "--sleep-quality", quality]
    if dry_run:
        print(f"[dry-run] 将执行：{' '.join(cmd)}")
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Apple Watch 睡眠数据同步")
    parser.add_argument("--auto",    action="store_true", help="自动模式（launchd 调用）")
    parser.add_argument("--dry-run", action="store_true", help="仅显示，不执行")
    parser.add_argument("--date",    default=None,        help="指定日期 YYYY-MM-DD")
    parser.add_argument("--status",  action="store_true", help="只显示当前睡眠数据，不初始化")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()

    SYNC_DIR.mkdir(exist_ok=True)

    data = read_sleep_data(target_date)

    if data is None:
        if args.auto:
            # 静默失败，记录日志
            log = SYNC_DIR / "daily.log"
            with open(log, "a") as f:
                f.write(f"[{target_date}] 未找到睡眠数据，跳过自动初始化\n")
        else:
            print(f"\n❌ 未找到 {target_date} 的睡眠数据")
            print(f"   预期路径：{SYNC_DIR}/sleep_{target_date}.json")
            print(f"\n   → 请确认「捷径」自动化已正确配置。")
            print(f"   → 或手动运行：python attention.py new-day --sleep-quality normal")
            print(f"\n   查看设置说明：bash setup_macos.sh --help")
        return

    quality, summary = classify_sleep(data)

    if args.status:
        print(f"\n🌙 {target_date} 睡眠数据")
        print(f"   来源：{data.get('source', 'Apple Watch')}")
        print(f"   {summary}")
        return

    print(f"\n🌙 睡眠同步：{summary}")

    run_new_day(quality, dry_run=args.dry_run)

    # 记录日志
    if args.auto:
        log = SYNC_DIR / "daily.log"
        with open(log, "a") as f:
            f.write(f"[{target_date}] {summary}\n")


if __name__ == "__main__":
    main()
