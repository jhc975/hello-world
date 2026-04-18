#!/bin/bash
# setup_macos.sh
# 在 macOS 上配置「每天上午10点自动拉取 Apple Watch 睡眠数据」的 launchd 定时任务
# 用法：bash setup_macos.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=$(which python3 2>/dev/null || echo "/usr/bin/python3")
SYNC_DIR="$HOME/.attention_sync"
PLIST_LABEL="com.attention.daily"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_PATH="$SYNC_DIR/daily.log"

# ── 帮助文档 ──────────────────────────────────────────────────────────────────
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  cat <<'HELP'

捷径（Shortcuts）配置说明
══════════════════════════════════════════════════════════════

目标：让 iPhone / Apple Watch 每天早晨自动将睡眠数据写入 JSON 文件，
      供 sleep_sync.py 读取。

─── 第一步：在 iPhone 上创建「捷径」────────────────────────────────

打开「捷径」App → 右上角 + → 搜索并按序添加以下动作：

 1. 【查找健康样本】
      - 类型：睡眠分析
      - 排序：开始时间（最新）
      - 数量限制：打开，1 条
      （这会获取最近一次睡眠记录）

 2. 【获取健康样本的详细信息】（重复4次，分别获取以下字段）
      - 睡眠阶段：深度睡眠   → 变量名：deep_min
      - 睡眠阶段：REM 睡眠   → 变量名：rem_min
      - 睡眠阶段：核心睡眠   → 变量名：core_min
      - 总时长（分钟）       → 变量名：total_min

 3. 【文本】（手动构建 JSON 字符串）
      复制粘贴以下内容（捷径会自动插入变量值）：
      ──────────────────────────────────────────
      {
        "date": "当前日期（格式 YYYY-MM-DD）",
        "total_sleep_minutes": 变量:total_min,
        "deep_sleep_minutes": 变量:deep_min,
        "rem_sleep_minutes": 变量:rem_min,
        "awakenings": 0,
        "efficiency": 0.85,
        "source": "Apple Watch"
      }
      ──────────────────────────────────────────
      注：「当前日期」使用捷径的「日期」动作 → 格式设为"自定义"→ yyyy-MM-dd

 4. 【存储文件】
      - 目标路径：iCloud Drive / 选择位置
      - 文件名：sleep_日期.json（日期同上步）
      - 位置：选「我的 iPhone」→「捷径」文件夹

─── 第二步：设置自动化 ────────────────────────────────────────────

捷径 App → 底部「自动化」→ + → 「一天中的时间」
  - 时间：08:00（设在起床后、10点同步前）
  - 运行：选择上方创建的捷径
  - 询问运行前：关闭（全自动）

─── 第三步：同步目录映射 ──────────────────────────────────────────

如果 Mac 和 iPhone 在同一 iCloud 账号：
  捷径文件会出现在 ~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/
  在 sleep_sync.py 中修改 SYNC_DIR 指向该路径，或设置软链接：

  ln -s ~/Library/Mobile\ Documents/iCloud~is~workflow~my~workflows/Documents \
        ~/.attention_sync

如果不用 iCloud Drive：
  可以把捷径存储目标改为「文件」App 中可访问的共享目录，
  或使用 AirDrop / 其他同步方案把 JSON 文件同步到 Mac。

─── 验证 ────────────────────────────────────────────────────────

  python3 sleep_sync.py --status          # 查看今日睡眠数据
  python3 sleep_sync.py --dry-run         # 模拟运行（不修改数据）
  cat ~/.attention_sync/daily.log         # 查看自动化运行日志

HELP
  exit 0
fi

# ── 安装 launchd 定时任务 ─────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  注意力规划系统 — macOS 自动化安装"
echo "══════════════════════════════════════════════════════════"
echo ""

# 检查 Python
if ! command -v python3 &>/dev/null; then
  echo "❌ 未找到 python3，请先安装 Python 3.10+ (brew install python)"
  exit 1
fi
PYTHON=$(which python3)
echo "✅ Python：$PYTHON ($(python3 --version))"

# 创建同步目录
mkdir -p "$SYNC_DIR"
echo "✅ 同步目录：$SYNC_DIR"

# 生成 launchd plist
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${SCRIPT_DIR}/sleep_sync.py</string>
    <string>--auto</string>
  </array>

  <!-- 每天上午 10:00 运行 -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>10</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>${LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_PATH}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>

  <!-- Mac 睡眠唤醒后仍执行（若10点时 Mac 在休眠则唤醒后立即补跑） -->
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST

echo "✅ launchd 配置：$PLIST_PATH"

# 加载定时任务
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load   "$PLIST_PATH"
echo "✅ 定时任务已加载（每天 10:00 自动运行）"

echo ""
echo "──────────────────────────────────────────────────────────"
echo "  下一步：配置 Apple Watch 捷径"
echo "──────────────────────────────────────────────────────────"
echo ""
echo "  运行以下命令查看详细捷径配置说明："
echo "  bash setup_macos.sh --help"
echo ""
echo "  验证安装："
echo "  launchctl list | grep attention      # 确认任务已注册"
echo "  python3 sleep_sync.py --status       # 查看今日睡眠数据"
echo "  python3 sleep_sync.py --dry-run      # 模拟运行"
echo "  cat $LOG_PATH  # 查看运行日志"
echo ""

# ── 卸载选项 ─────────────────────────────────────────────────────────────────
if [[ "$1" == "--uninstall" ]]; then
  launchctl unload "$PLIST_PATH" 2>/dev/null && rm -f "$PLIST_PATH"
  echo "✅ 已卸载定时任务"
fi
