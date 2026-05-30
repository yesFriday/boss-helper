#!/usr/bin/env bash
set -e

echo "================================"
echo " 安装依赖"
echo "================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 没找到 python3，先装 Python 吧"
    exit 1
fi
echo "✅ Python $(python3 --version)"

# 装 pip 依赖
echo ""
echo ">> pip install..."
pip3 install -r requirements.txt

# 装 Playwright 浏览器
echo ""
echo ">> 装 Playwright 浏览器（Chromium + Firefox）..."
python3 -m playwright install chromium firefox 2>&1 | tail -5

echo ""
echo "================================"
echo " 搞定了，跑一下试试："
echo ""
echo "  BOSS直聘："
echo "    python backend/firefox.py --login   # 首次扫码登录"
echo "    python backend/firefox.py           # 采集数据"
echo ""
echo "  智联招聘："
echo "    python backend/scraper.py"
echo ""
echo "  或者搜别的岗位："
echo "    python backend/scraper.py --keywords \"Java,Go,Python\""
echo "================================"
