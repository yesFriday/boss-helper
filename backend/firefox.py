#!/usr/bin/env python3
"""
BOSS直聘 AI Agent 岗位采集工具

流程:
  1. 搜索列表页 → 提取基本信息（标题、薪资、公司、城市、经验、学历、链接）
  2. 逐个访问详情页 → 提取"岗位技能"原文输出

用法:
  python3 boss_firefox.py                     # 采集+分析
  python3 boss_firefox.py --login             # 首次扫码登录
  python3 boss_firefox.py --headless          # 无头模式
"""

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from backend.logger import get_logger

log = get_logger("firefox")

# PyInstaller 冻结环境下，Playwright 会在临时解包目录(_MEIxxx)里找浏览器导致
# "Executable doesn't exist"。强制指向共享安装位置(%LOCALAPPDATA%\ms-playwright)。
if getattr(sys, "frozen", False):
    _shared_browsers = Path.home() / "AppData" / "Local" / "ms-playwright"
    if _shared_browsers.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_shared_browsers))
        log.info(f"[冻结模式] 浏览器目录: {_shared_browsers}")
    else:
        log.warning(
            f"[冻结模式] 未找到共享浏览器目录 {_shared_browsers}，"
            "请先运行 playwright install"
        )

# Windows 编码修复（原地重配置，不替换对象——替换会导致测试捕获流被意外关闭）
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── 配置 ──
TODAY = date.today().isoformat()
DATE_STR = date.today().strftime("%Y-%m-%d")

KEYWORDS = [
    "AI Agent",
    "AI产品经理",
    "电商",
    "机械",
    "化工",
    "外贸",
]

# BOSS直聘城市代码
CITIES = {
    # 山东省
    "济南": "101120100",
    "青岛": "101120200",
    "淄博": "101120300",
    "德州": "101120400",
    "烟台": "101120500",
    "潍坊": "101120600",
    "济宁": "101120700",
    "泰安": "101120800",
    "临沂": "101120900",
    "菏泽": "101121000",
    "滨州": "101121100",
    "东营": "101121200",
    "威海": "101121300",
    "枣庄": "101121400",
    "日照": "101121500",
    "聊城": "101121700",
    # 一线城市
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    # 新一线城市
    "成都": "101270100",
    "杭州": "101210100",
    "武汉": "101200100",
    "南京": "101190100",
    "重庆": "101040100",
    "西安": "101110100",
    "长沙": "101250100",
    "天津": "101030100",
    "苏州": "101190400",
    "郑州": "101180100",
    "东莞": "101281600",
    "沈阳": "101070100",
    "宁波": "101210400",
    "昆明": "101290100",
    # 其他省会城市
    "合肥": "101220100",
    "福州": "101230100",
    "厦门": "101230200",
    "南昌": "101240100",
    "贵阳": "101260100",
    "南宁": "101300100",
    "太原": "101100100",
    "石家庄": "101090100",
    "哈尔滨": "101050100",
    "长春": "101060100",
    "兰州": "101160100",
    "乌鲁木齐": "101130100",
    "呼和浩特": "101080100",
    "拉萨": "101140100",
    "西宁": "101150100",
    "银川": "101170100",
    "海口": "101310100",
    "三亚": "101310200",
    "全国": "100010000",
}

from backend.path_config import get_boss_data_dir

OUTPUT_DIR = Path.home() / "AI" / "岗位日报"
STATE_FILE = get_boss_data_dir() / "firefox_state.json"
PROFILE_DIR = get_boss_data_dir() / "firefox_user_data"

ANTI_DETECT = """
// ── 核心：隐藏 webdriver 标记 ──
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
try { delete Object.getPrototypeOf(navigator).webdriver; } catch(e) {}

// ── 语言 ──
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});

// ── 硬件（桌面端典型值）──
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});

// ── screen 与 viewport 保持一致 ──
const fixScreen = () => {
    const w = window.innerWidth || 1280;
    const h = window.innerHeight || 800;
    Object.defineProperty(screen, 'width',  {get: () => w});
    Object.defineProperty(screen, 'height', {get: () => h});
    Object.defineProperty(screen, 'availWidth',  {get: () => w});
    Object.defineProperty(screen, 'availHeight', {get: () => h});
    Object.defineProperty(screen, 'colorDepth', {get: () => 24});
    Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
};
fixScreen();
window.addEventListener('resize', fixScreen);

// ── 时区 ──
if (Intl && Intl.DateTimeFormat) {
    const origResolved = Intl.DateTimeFormat.prototype.resolvedOptions;
    Intl.DateTimeFormat.prototype.resolvedOptions = function() {
        const r = origResolved.call(this);
        r.timeZone = 'Asia/Shanghai';
        return r;
    };
}

// ── canvas 指纹干扰：轻微噪声扰动 ──
try {
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 10 && this.height > 10) {
            const imgData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imgData.data.length; i += 4) {
                imgData.data[i] ^= 1;  // R channel ±1 bit
            }
            ctx.putImageData(imgData, 0, 0);
        }
        return origToDataURL.apply(this, arguments);
    };
} catch(e) {}

// ── WebGL 指纹一致性 ──
try {
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        // UNMASKED_VENDOR / UNMASKED_RENDERER
        if (p === 37445) return 'Google Inc. (Intel)';
        if (p === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0)';
        return getParam.call(this, p);
    };
} catch(e) {}

// ── 权限通知 ──
if (window.Permissions) {
    const orig = window.Permissions.prototype.query;
    window.Permissions.prototype.query = function(d) {
        if (d.name === 'notifications') return Promise.resolve({state: 'prompt'});
        return orig.call(this, d);
    };
}

// ── navigator.connection ──
try {
    Object.defineProperty(navigator, 'connection', {
        get: () => ({effectiveType: '4g', rtt: 50, downlink: 10, saveData: false})
    });
} catch(e) {}
"""

# ── 技能词库（仅分析用）──
SKILL_MAP = {
    "编程语言": {
        "Python",
        "Java",
        "Go",
        "Golang",
        "Rust",
        "C++",
        "C#",
        "C",
        "PHP",
        "Ruby",
        "Swift",
        "Kotlin",
        "Scala",
        "TypeScript",
        "JavaScript",
        "Node.js",
    },
    "前端": {"React", "Vue", "Angular", "Next.js", "HTML", "CSS", "Tailwind"},
    "AI/ML框架": {
        "PyTorch",
        "TensorFlow",
        "Transformers",
        "vLLM",
        "ONNX",
        "HuggingFace",
        "GGUF",
        "Stable Diffusion",
        "Diffusion",
        "Vision",
        "Multimodal",
    },
    "AI框架/工具": {
        "LangChain",
        "LangGraph",
        "LlamaIndex",
        "AutoGen",
        "CrewAI",
        "Dify",
        "Coze",
        "MCP",
    },
    "大模型技术": {
        "RAG",
        "Fine-tuning",
        "Finetune",
        "微调",
        "SFT",
        "RLHF",
        "LoRA",
        "QLoRA",
        "Prompt",
        "Function Calling",
        "Tool Calling",
        "Agent",
        "Multi-Agent",
        "Embedding",
        "LLM",
        "AI Agent",
        "AIGC",
    },
    "数据库/中间件": {
        "MySQL",
        "PostgreSQL",
        "Redis",
        "MongoDB",
        "Elasticsearch",
        "Milvus",
        "FAISS",
        "Chroma",
        "Qdrant",
        "Pinecone",
        "Weaviate",
        "Kafka",
        "RabbitMQ",
    },
    "部署/架构": {
        "Docker",
        "Kubernetes",
        "K8s",
        "FastAPI",
        "Flask",
        "Django",
        "Spring",
        "Nginx",
        "gRPC",
        "GraphQL",
        "WebSocket",
        "REST",
        "RESTful",
        "CI/CD",
        "GitHub Actions",
        "Linux",
        "GPU",
        "CUDA",
    },
    "云平台": {"AWS", "GCP", "Azure", "阿里云", "腾讯云"},
    "其他": {
        "数据结构",
        "算法",
        "系统设计",
        "架构",
        "微服务",
        "高并发",
        "分布式",
        "设计模式",
        "OOP",
        "TDD",
        "单元测试",
        "测试",
    },
}
ALL_SKILLS = {s for v in SKILL_MAP.values() for s in v}
MY_SKILLS = {
    s.lower()
    for v in {
        "编程语言": {"Python", "TypeScript", "JavaScript"},
        "AI框架/工具": {"LangChain", "LangGraph", "AutoGen", "CrewAI", "Dify", "Coze"},
        "大模型技术": {
            "LLM",
            "AI Agent",
            "RAG",
            "微调",
            "MCP",
            "Prompt Engineering",
            "Function Calling",
            "Tool Calling",
            "Embedding",
        },
        "数据库/向量库": {"MySQL", "Milvus", "FAISS", "Chroma", "Qdrant"},
        "部署/运维": {"Docker", "FastAPI", "Kubernetes"},
        "AI平台/模型": {"Claude", "OpenAI", "GPT"},
    }.values()
    for s in v
}


def decode_salary(text):
    return "".join(str(ord(c) - 0xE030) if 0xE030 <= ord(c) <= 0xE039 else c for c in text)


def salary_ok(text):
    if not text:
        return False
    nums = re.findall(
        r"(\d+)",
        re.sub(r"[^\d-]", "", text.replace("~", "-").replace("K", "").replace("k", "")),
    )
    if len(nums) < 2:
        return False
    l, h = int(nums[0]), int(nums[1])
    if l < 5 and h < 20:
        l *= 10
        h *= 10
    return 15 <= l and h <= 35


def pause(a=1.0, b=3.0):
    time.sleep(random.uniform(a, b))


def parse_skills(text):
    tl = text.lower()
    r = defaultdict(list)
    for cat, skills in SKILL_MAP.items():
        for s in skills:
            if s.lower() in tl:
                r[cat].append(s)
    return dict(r)


# ══════════════════════════════════════
#  浏览器
# ══════════════════════════════════════


class BossScraper:
    def __init__(self, headless=False):
        self.headless = headless
        self._pw = self._br = self._ctx = None
        self.page = None
        self.search_cancelled = False  # 搜索取消标志

    def start(self):
        self._pw = sync_playwright().start()
        try:
            self._start_context()
        except Exception:
            # 原子性清理:Playwright 启动后任何失败都必须 stop,否则其内部事件循环
            # 会留在 pw 线程,导致后续所有启动都报 "Sync API inside the asyncio loop"
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
            self._ctx = None
            self.page = None
            raise

    def _start_context(self):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        kw = {
            "headless": self.headless,
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        }
        self._ctx = self._pw.firefox.launch_persistent_context(str(PROFILE_DIR), **kw)
        self._br = None

        # 持久化 profile 自动管理 cookies，不额外 add_cookies 避免冲突
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                cookies = state.get("cookies") or []
                if cookies:
                    for c in cookies:
                        try:
                            self._ctx.add_cookies([c])
                        except Exception:
                            pass
            except Exception:
                pass

        self._ctx.add_init_script(ANTI_DETECT)
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self.page.set_default_timeout(30000)

    def close(self):
        if self._ctx:
            try:
                self._ctx.close()
            except Exception:
                pass
        elif self._br:
            self._br.close()
        if self._pw:
            self._pw.stop()
        self._kill_lingering_firefox()

    def _kill_lingering_firefox(self):
        """close 后 Firefox 若未退净会持有 profile 锁,导致下次启动等锁 2 分钟。
        给 3 秒优雅退出时间,然后强杀命令行里带本 profile 路径的 firefox 进程。"""
        time.sleep(3)
        try:
            cmd = (
                "Get-CimInstance Win32_Process -Filter \"Name='firefox.exe'\" | "
                f"Where-Object {{ $_.CommandLine -like '*{PROFILE_DIR}*' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, timeout=20,
            )
        except Exception:
            pass

    def _body_text(self, limit=1500):
        try:
            return self.page.inner_text("body")[:limit]
        except Exception:
            return ""

    def _login_prompt_visible(self):
        """判断当前页面是否真的落在登录/扫码态，避免误判普通详情页。"""
        try:
            url = (self.page.url or "").lower()
        except Exception:
            url = ""

        explicit_login_paths = (
            "/web/user/",
            "/login/",
            "ka=header-login",
            "login?redirect=",
        )
        if any(path in url for path in explicit_login_paths):
            return True

        body = self._body_text(4000)

        # 详情页/聊天页的已登录特征，优先级高于任意“登录”字样。
        authenticated_indicators = (
            "职位描述",
            "岗位职责",
            "任职要求",
            "公司介绍",
            "竞争力分析",
            "立即沟通",
            "立即聊",
            "已沟通",
            "继续沟通",
            "聊天",
            "消息",
            "沟通中",
            "发简历",
        )
        if any(text in body for text in authenticated_indicators):
            return False

        strong_prompts = (
            "请登录",
            "扫码登录",
            "密码登录",
            "验证码登录",
            "微信扫码",
            "登录BOSS直聘",
        )
        if not any(text in body for text in strong_prompts):
            return False

        try:
            return self.page.evaluate("""() => {
                const visible = el => {
                    if (!el) return false;
                    const style = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    const ariaHidden = el.getAttribute('aria-hidden');
                    return style
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && style.opacity !== '0'
                        && ariaHidden !== 'true'
                        && rect.width > 0
                        && rect.height > 0;
                };

                const selectors = [
                    'input[placeholder*="手机号"]',
                    'input[placeholder*="验证码"]',
                    'input[type="password"]',
                    '.qrcode-img',
                    'img[class*="qrcode"]',
                    '[class*="login-panel"]',
                    '[class*="login-modal"]',
                    '[class*="sign-form"]',
                    '[class*="user-sign"]',
                ];

                return selectors.some(sel =>
                    Array.from(document.querySelectorAll(sel)).some(visible)
                );
            }""")
        except Exception:
            # 页面内容已明确出现强登录提示，但 JS 检测失败时宁可保守返回 False，
            # 避免误把普通详情页当成掉线。
            return False

    def is_logged_in_page(self):
        """当前页面是否能作为已登录态使用；about:blank 属于未知，不当作过期。"""
        try:
            url = self.page.url
        except Exception:
            return False
        if url == "about:blank":
            return True
        return not self._login_prompt_visible()

    def login(self):
        self.page.goto("https://www.zhipin.com/web/user/?ka=header-login")
        pause(2, 4)
        self.page.bring_to_front()
        log.info("浏览器已打开，请扫码登录")
        last = self.page.url
        logged_in = False
        for i in range(600):
            time.sleep(1)
            try:
                url = self.page.evaluate("window.location.href")
            except:
                continue
            if (
                any(p in url for p in ["/web/geek", "/web/geek/chat", "/job_detail"])
                and not self._login_prompt_visible()
            ):
                log.info("登录成功")
                logged_in = True
                break
            last = url
            if i > 0 and i % 30 == 0:
                log.debug("等待扫码中: %ds", i)
        if not logged_in:
            raise TimeoutError("扫码登录超时或未确认进入已登录页面")
        state = self._ctx.storage_state()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        log.info("登录状态已保存")

        # 预热：导航到聊天页验证 session 稳定性，确保 token 生效
        try:
            self.page.goto("https://www.zhipin.com/web/geek/chat", wait_until="load", timeout=30000)
            pause(3, 5)
            if not self._login_prompt_visible():
                log.info("会话预热成功")
            else:
                log.warning("预热时仍检测到登录提示，可能需要手动刷新页面")
        except Exception as e:
            log.error("会话预热失败: %s", e, exc_info=True)

    # ── 搜索列表页 ──

    def search(self, keyword, city_code="101280100"):
        """搜索关键词，返回岗位列表"""
        url = "https://www.zhipin.com/web/geek/job?query=%s&city=%s" % (
            quote_plus(keyword),
            city_code,
        )
        self.page.goto(url, wait_until="load", timeout=45000)
        pause(3, 5)
        self._scroll_all()

        dom_jobs = self._extract_job_cards()
        if dom_jobs:
            # 点击每个卡片提取 HR 活跃时间
            dom_jobs = self._enrich_hr_active_time(dom_jobs)
            return dom_jobs

        lines = [l.strip() for l in self.page.inner_text("body").split("\n") if l.strip()]

        # 薪资行定位
        sal_idx = [i for i, l in enumerate(lines) if re.search(r"\d+[-~]\d+K", decode_salary(l), re.I)]

        jobs = []
        for n, si in enumerate(sal_idx):
            if n > 0 and si - sal_idx[n - 1] < 3:
                continue
            if si == 0:
                continue
            title = lines[si - 1]
            if not (2 < len(title) < 60):
                continue

            salary = decode_salary(lines[si])
            company = exp = edu = city = ""
            end = sal_idx[n + 1] if n + 1 < len(sal_idx) else min(si + 10, len(lines))
            for j in range(si + 1, min(end, len(lines))):
                ln = lines[j]
                if "经验" in ln or "应届" in ln:
                    exp = ln
                elif re.search(r"本科|硕士|博士|大专|学历不限", ln):
                    edu = ln
                elif "·" in ln and len(ln) < 30:
                    city = ln
                elif (
                    not company
                    and len(ln) > 2
                    and len(ln) < 40
                    and not re.search(r"年|学历|大专|本科|硕士|博士|不限|应届|·", ln)
                ):
                    company = ln

            jobs.append(
                {
                    "title": title,
                    "salary": salary,
                    "company": company,
                    "experience": exp,
                    "education": edu,
                    "city": city,
                    "url": "",
                    "description": "",
                    "hr_name": "",
                    "hr_title": "",
                }
            )

        # 合并链接
        links = self._extract_links()
        if links:
            lm = {l["title"][:12]: l["href"] for l in links if l["title"][:12]}
            for j in jobs:
                if not j["url"] and j["title"][:12] in lm:
                    j["url"] = lm[j["title"][:12]]
        return jobs

    def _filter_by_welfare(self, jobs, welfare_keywords):
        """福利筛选：AND逻辑，所有关键词都必须匹配。"""
        if not welfare_keywords:
            return jobs
        filtered = []
        for j in jobs:
            tags = " ".join(j.get("welfareList", []) or [])
            if not tags:
                tags = j.get("description", "") or ""
            if all(kw in tags for kw in welfare_keywords):
                filtered.append(j)
        return filtered

    def _filter_by_expect(self, jobs, salary_expect=None, experience_expect=None):
        """按期望薪资和工作年限过滤（闭区间判断）。
        salary_expect: 用户期望薪资(K)，判断是否在岗位薪资 [min, max] 内
        experience_expect: 用户工作年限(年)，判断是否在岗位经验 [min, max] 内
        """
        if salary_expect is None and experience_expect is None:
            return jobs
        filtered = []
        for j in jobs:
            # 薪资过滤
            if salary_expect is not None:
                salary_text = j.get("salary", "") or ""
                nums = re.findall(r"(\d+)", salary_text)
                if len(nums) >= 2:
                    lo, hi = int(nums[0]), int(nums[1])
                    # 处理 "1-2K" 这种小数字情况
                    if lo < 5 and hi < 20:
                        lo *= 10
                        hi *= 10
                    if not (lo <= salary_expect <= hi):
                        continue
                elif len(nums) == 1:
                    val = int(nums[0])
                    if val < 5:
                        val *= 10
                    if val != salary_expect:
                        continue
                else:
                    continue
            # 经验过滤
            if experience_expect is not None:
                exp_text = j.get("experience", "") or ""
                nums = re.findall(r"(\d+)", exp_text)
                if len(nums) >= 2:
                    lo, hi = int(nums[0]), int(nums[1])
                    if not (lo <= experience_expect <= hi):
                        continue
                elif len(nums) == 1:
                    val = int(nums[0])
                    if val != experience_expect:
                        continue
                else:
                    continue
            filtered.append(j)
        return filtered

    def _filter_by_hr_active(self, jobs, exclude_statuses=None):
        """按 HR 活跃时间过滤，排除不活跃的 HR。
        exclude_statuses: 要排除的活跃状态列表，如 ["半年前活跃", "一年前活跃"]
        """
        if not exclude_statuses:
            return jobs
        filtered = []
        for j in jobs:
            active = (j.get("hr_active_time") or "").strip()
            if not active:
                filtered.append(j)  # 没有活跃信息的保留
                continue
            should_exclude = False
            for status in exclude_statuses:
                if status in active:
                    should_exclude = True
                    break
            if not should_exclude:
                filtered.append(j)
        return filtered

    def _extract_job_cards(self):
        """优先从岗位卡片 DOM 提取，避免正文行号变化导致链接和岗位错配。"""
        try:
            rows = self.page.evaluate("""() => {
                const pickText = (root, selectors) => {
                    for (const sel of selectors) {
                        const el = root.querySelector(sel);
                        const text = (el && el.innerText || '').trim();
                        if (text) return text;
                    }
                    return '';
                };
                const linesOf = (root) => (root.innerText || '')
                    .split('\\n')
                    .map(s => s.trim())
                    .filter(Boolean);
                const cards = [];
                const seen = new Set();
                document.querySelectorAll('a[href*="/job_detail/"]').forEach(a => {
                    const href = a.href || a.getAttribute('href') || '';
                    if (!href || seen.has(href)) return;
                    const card = a.closest('.job-card-wrapper, .job-card-body, .job-primary, li, .job-list-box, .search-job-result') || a;
                    const lines = linesOf(card);
                    let title = pickText(card, [
                        '.job-name', '.job-title', '.job-card-left .job-name',
                        '[class*="job-name"]', '[class*="job-title"]'
                    ]) || (a.innerText || '').trim().split('\\n')[0] || lines[0] || '';
                    let salary = pickText(card, ['.salary', '.red', '[class*="salary"]'])
                        || lines.find(x => /\\d+[-~]\\d+K/i.test(x)) || '';
                    let company = pickText(card, [
                        '.company-name', '.brand-name', '.company-text',
                        '[class*="company-name"]', '[class*="brand-name"]'
                    ]);
                    let city = pickText(card, ['.job-area', '[class*="job-area"]'])
                        || lines.find(x => x.includes('·') && x.length < 40) || '';
                    let experience = lines.find(x => /经验|应届|在校|不限/.test(x) && x.length < 30) || '';
                    let education = lines.find(x => /本科|硕士|博士|大专|学历不限|中专|高中/.test(x) && x.length < 30) || '';
                    // HR 活跃时间（不在卡片DOM里，后续通过点击卡片从右边详情面板获取）
                    let hrActiveTime = '';
                    if (!company) {
                        company = lines.find(x =>
                            x !== title && x !== salary && x !== city &&
                            !/经验|应届|在校|不限|本科|硕士|博士|大专|学历|·|\\d+[-~]\\d+K/i.test(x) &&
                            x.length > 1 && x.length < 40
                        ) || '';
                    }
                    title = title.replace(/\\s+/g, ' ').trim();
                    if (title && salary) {
                        seen.add(href);
                        cards.push({title, salary, company, city, experience, education, url: href, hrActiveTime});
                    }
                });
                return cards;
            }""")
        except Exception:
            return []


        jobs = []
        seen = set()
        for row in rows or []:
            url = (row.get("url") or "").strip()
            title = (row.get("title") or "").strip()
            if not url or not title or url in seen:
                continue
            seen.add(url)
            jobs.append(
                {
                    "title": title,
                    "salary": decode_salary((row.get("salary") or "").strip()),
                    "company": (row.get("company") or "").strip(),
                    "experience": (row.get("experience") or "").strip(),
                    "education": (row.get("education") or "").strip(),
                    "city": (row.get("city") or "").strip(),
                    "url": url,
                    "description": "",
                    "hr_name": "",
                    "hr_title": "",
                    "hr_active_time": (row.get("hrActiveTime") or "").strip(),
                }
            )
        # 调试：打印 HR 活跃时间提取结果
        hr_with_active = [j for j in jobs if j.get("hr_active_time")]
        log.info(f"[搜索] 共 {len(jobs)} 条，有 HR 活跃时间: {len(hr_with_active)} 条")
        if hr_with_active:
            for j in hr_with_active[:3]:
                log.info(f"[搜索]   {j['title']} → {j['hr_active_time']}")
        return jobs

    def _enrich_hr_active_time(self, jobs):
        """点击每个职位卡片，从右边详情面板提取 HR 活跃时间。"""
        try:
            # 获取所有职位链接
            links = self.page.query_selector_all('a[href*="/job_detail/"]')
            if not links:
                log.info("[搜索] 未找到职位链接，跳过 HR 活跃时间提取")
                return jobs

            log.info(f"[搜索] 开始提取 HR 活跃时间，共 {len(links)} 个链接")
            # 创建 URL 到 job 的映射
            url_to_job = {j.get("url", ""): j for j in jobs}
            log.info(f"[搜索] job URL 样本: {list(url_to_job.keys())[:3]}")

            skip_no_href = 0
            skip_no_job = 0
            skip_has_data = 0
            clicked = 0

            for i, link in enumerate(links):
                if self.search_cancelled:
                    log.info(f"[搜索] 用户取消搜索，停止提取 HR 活跃时间（已完成 {i}/{len(links)}）")
                    break

                try:
                    href = link.get_attribute("href") or ""
                    if not href:
                        skip_no_href += 1
                        continue

                    # get_attribute("href") 返回相对路径，补全为完整 URL
                    if href.startswith("/"):
                        href = "https://www.zhipin.com" + href

                    # 找到对应的 job
                    job = url_to_job.get(href)
                    if not job:
                        skip_no_job += 1
                        if i < 3:
                            log.info(f"[搜索] 链接未匹配: {href}")
                        continue

                    # 如果已经有 HR 活跃时间，跳过
                    if job.get("hr_active_time"):
                        skip_has_data += 1
                        continue

                    # 点击卡片，等待右边详情面板渲染
                    clicked += 1
                    link.click()
                    time.sleep(0.5)

                    # 从页面级别提取 HR 活跃时间（右边详情面板）
                    hr_active = self.page.evaluate("""() => {
                        const onlineTag = document.querySelector('.boss-online-tag');
                        if (onlineTag && onlineTag.textContent.trim() === '在线') {
                            return '在线';
                        }
                        const activeTimeElement = document.querySelector('.boss-active-time');
                        return activeTimeElement ? activeTimeElement.textContent.trim() : '';
                    }""")

                    if hr_active:
                        job["hr_active_time"] = hr_active
                        log.info(f"[搜索] HR活跃: {job['title']} → {hr_active}")

                except Exception as e:
                    log.debug(f"[搜索] 提取 HR 活跃时间失败: {e}")
                    continue

        except Exception as e:
            log.warning(f"[搜索] _enrich_hr_active_time 异常: {e}")

        # 统计结果
        hr_with_active = [j for j in jobs if j.get("hr_active_time")]
        log.info(f"[搜索] HR 活跃时间提取完成: 点击{clicked}次, 跳过[无href:{skip_no_href}, 未匹配:{skip_no_job}, 已有数据:{skip_has_data}], 有数据:{len(hr_with_active)}/{len(jobs)}")
        return jobs

    def _scroll_all(self, min_jobs=200):
        """持续滚动加载岗位，直到达到 min_jobs 或无新内容。"""
        try:
            prev_count = 0
            no_new_rounds = 0
            while no_new_rounds < 3:
                # 检查是否取消搜索
                if self.search_cancelled:
                    log.info("[搜索] 用户取消搜索，停止滚动")
                    break
                h = self.page.evaluate("document.body.scrollHeight")
                for p in range(0, int(h) + 400, 400):
                    if self.search_cancelled:
                        break
                    self.page.evaluate("window.scrollTo(0,%d)" % p)
                    time.sleep(random.uniform(0.3, 0.6))
                time.sleep(1)
                count = len(self.page.query_selector_all('a[href*="/job_detail/"]'))
                if count >= min_jobs:
                    break
                if count == prev_count:
                    no_new_rounds += 1
                else:
                    no_new_rounds = 0
                prev_count = count
        except:
            pass

    def _extract_links(self):
        try:
            return self.page.evaluate("""()=>{
                const r=[];const s=new Set();
                document.querySelectorAll('a[href*="/job_detail/"]').forEach(a=>{
                    const h=a.href,t=(a.innerText||'').trim();
                    if(h&&t&&!s.has(h)&&t.length<60){s.add(h);r.push({href:h,title:t.substring(0,60)});}
                });return r;
            }""")
        except:
            return []

    # ── 详情页 ──

    def fetch_detail(self, url):
        """访问详情页，提取岗位描述 + HR/招聘者信息"""
        result = {"description": "", "hr_name": "", "hr_title": ""}
        try:
            self.page.goto(url, wait_until="load", timeout=45000)
            pause(2, 4)

            # ── 提取招聘者信息 ──
            try:
                hr_info = self.page.evaluate("""() => {
                    const body = document.body.innerText || '';
                    const lines = body.split('\\n').map(l => l.trim()).filter(Boolean);
                    let hrName = '', hrTitle = '';
                    for (let i = 0; i < lines.length; i++) {
                        const l = lines[i];
                        // BOSS直聘招聘者区域: 通常 "HR" "招聘者" "经理" 等标识
                        if (l.includes('HR') || l.includes('招聘者') || l.includes('招聘经理') ||
                            l.includes('人事') || l.includes('HRBP') || l.includes('猎头')) {
                            // 上一行或当前行可能是名字
                            if (i > 0 && lines[i-1].length <= 6 && !/\\d|省|市|区|路|号|招聘|公司|BOSS/.test(lines[i-1])) {
                                hrName = lines[i-1];
                            }
                            hrTitle = l;
                            break;
                        }
                    }
                    // 也尝试用选择器找招聘者信息区域
                    const bossSelectors = [
                        '.boss-info-attr', '.boss-info', '.recruiter-info',
                        '.boss-name', '.recruiter-name', '[class*="boss"]',
                    ];
                    for (const sel of bossSelectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim()) {
                            const t = el.innerText.trim();
                            if (t.length <= 15) {
                                if (!hrName) hrName = t;
                                break;
                            }
                        }
                    }
                    return {hrName, hrTitle};
                }""")
                result["hr_name"] = (hr_info.get("hrName") or "").strip()
                result["hr_title"] = (hr_info.get("hrTitle") or "").strip()
            except:
                pass

            # ── 提取岗位描述 ──
            body = self.page.inner_text("body")
            lines = [l.strip() for l in body.split("\n") if l.strip()]

            skill_lines = []
            capture = False
            for l in lines:
                if "职位描述" in l or "岗位职责" in l:
                    capture = True
                    continue
                if capture:
                    if any(
                        stop in l
                        for stop in [
                            "公司介绍",
                            "工商信息",
                            "BOSS 安全提示",
                            "竞争力分析",
                        ]
                    ):
                        break
                    skill_lines.append(l)
            result["description"] = "\n".join(skill_lines) if skill_lines else ""

            # 如果 JS 没抓到招聘者信息，从文本中尝试解析
            if not result["hr_name"]:
                for i, l in enumerate(lines):
                    if l in ("HR", "招聘者", "招聘经理", "HRBP", "人事", "猎头"):
                        if i > 0 and len(lines[i - 1]) <= 6:
                            result["hr_name"] = lines[i - 1]
                            result["hr_title"] = l
                            break

        except Exception:
            pass
        return result


# ══════════════════════════════════════
#  分析
# ══════════════════════════════════════


def skill_gap(jobs):
    c = Counter()
    for j in jobs:
        text = (j.get("description") or "") + " " + (j.get("title") or "")
        seen = set()
        for cat, skills in parse_skills(text).items():
            for s in skills:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    c[s] += 1
    have, miss = [], []
    for s, n in c.most_common():
        (have if s.lower() in MY_SKILLS else miss).append({"skill": s, "count": n})
    return {"have": have, "missing": miss, "total": len(jobs)}


# ══════════════════════════════════════
#  输出
# ══════════════════════════════════════


def output_report(jobs):
    lines = ["# 招聘日报 · %s\n" % DATE_STR]
    lines.append("> 来源：**BOSS直聘** · 无薪资限制 · 共 %d 条\n---\n" % len(jobs))

    for i, j in enumerate(jobs, 1):
        lines.append("### %d. %s %s" % (i, j["title"], j["salary"]))
        lines.append("- 公司: %s" % (j.get("company") or "未显示"))
        if j.get("city"):
            lines.append("- 城市: %s" % j["city"])
        if j.get("experience"):
            lines.append("- 经验: %s" % j["experience"])
        if j.get("education"):
            lines.append("- 学历: %s" % j["education"])
        if j.get("hr_name"):
            lines.append("- 👤 招聘者: %s (%s)" % (j["hr_name"], j.get("hr_title") or ""))
        if j.get("url"):
            lines.append("- 链接: %s" % j["url"])
        desc = j.get("description", "")
        if desc:
            lines.append("- 岗位技能：%s" % desc[:600])
        lines.append("---\n")
    lines.append("\n*数据采集于 %s，BOSS直聘*\n" % DATE_STR)
    return "\n".join(lines)


def skill_report(gap):
    lines = ["# AI Agent 技能差距分析报告 · %s\n" % DATE_STR]
    lines.append("> 基于 BOSS 直聘 %d 个岗位\n---\n" % gap["total"])
    lines.append("## 一、✅ 你已拥有的技能\n")
    for item in gap["have"]:
        lines.append("- **%s**: %d个岗位" % (item["skill"], item["count"]))
    lines.append("\n## 二、🔍 需要查漏补缺\n")
    for item in gap["missing"][:30]:
        p = "🔴" if item["count"] >= 10 else "🟡" if item["count"] >= 5 else "🟢"
        lines.append("- %s **%s**: %d个岗位" % (p, item["skill"], item["count"]))
    return "\n".join(lines)


# ══════════════════════════════════════
#  主流程
# ══════════════════════════════════════


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--headless", action="store_true", default=False)
    ap.add_argument("--keywords")
    ap.add_argument("--output", default=str(OUTPUT_DIR))
    ap.add_argument("--max-jobs", type=int, default=64)
    args = ap.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else KEYWORDS

    if not STATE_FILE.exists() and not args.login:
        log.error("请先运行: python3 boss_firefox.py --login")
        sys.exit(1)

    sc = BossScraper(headless=args.headless)
    sc.start()
    try:
        if args.login:
            sc.login()
            return

        # Phase 1: 搜索列表（关键词 × 城市）
        all_jobs = []
        seen = set()
        for city_name, city_code in CITIES.items():
            for kw in keywords:
                if len(all_jobs) >= args.max_jobs:
                    break
                log.info("搜索: 「%s」@ %s", kw, city_name)
                try:
                    jobs = sc.search(kw, city_code)
                except Exception as e:
                    log.error("搜索失败: %s", e)
                    continue
                ok = []
                for j in jobs:
                    key = j["title"] + j["salary"] + j.get("company", "")
                    if key not in seen:
                        seen.add(key)
                        j["city"] = city_name  # 标记城市
                        ok.append(j)
                log.info("%d条, 去重后%d条(累计%d)", len(jobs), len(ok), len(all_jobs))
                all_jobs.extend(ok)
                if len(all_jobs) >= args.max_jobs:
                    log.info("已达上限%d条", args.max_jobs)
                    break
                pause(2, 4)
            if len(all_jobs) >= args.max_jobs:
                break

        log.info("共%d条", len(all_jobs))
        if not all_jobs:
            return

        # Phase 2: 逐个访问详情页，提取岗位技能 + 招聘者信息
        log.info("开始采集岗位详情（共%d条）...", len(all_jobs))
        success = 0
        for i, j in enumerate(all_jobs):
            if not j.get("url"):
                continue
            log.debug("[%d/%d] %s", i + 1, len(all_jobs), j["title"][:25])
            detail = sc.fetch_detail(j["url"])
            if detail["description"]:
                j["description"] = detail["description"]
                success += 1
            j["hr_name"] = detail.get("hr_name", "")
            j["hr_title"] = detail.get("hr_title", "")
            if detail["description"]:
                log.info("[%d/%d] %s - %d字 | HR: %s", i + 1, len(all_jobs), j["title"][:25], len(detail["description"]), j["hr_name"] or "未识别")
            else:
                log.warning("[%d/%d] %s - 无描述 | HR: %s", i + 1, len(all_jobs), j["title"][:25], j["hr_name"] or "未识别")
            time.sleep(random.uniform(1.5, 3.0))

        log.info("详情采集: %d/%d条成功", success, len(all_jobs))

        # 分析输出到终端即可
        gap = skill_gap(all_jobs)
        log.info("=" * 60)
        log.info("技能差距分析")
        log.info("=" * 60)
        for item in gap["have"][:10]:
            log.info("已掌握 %s: %d个岗位", item["skill"], item["count"])
        for item in gap["missing"][:15]:
            p = "[高]" if item["count"] >= 10 else "[中]" if item["count"] >= 5 else "[低]"
            log.info("需补充 %s %s: %d个岗位", p, item["skill"], item["count"])

        # 输出——招聘日报 + CSV 数据文件
        with open(out_dir / ("招聘日报_%s.md" % DATE_STR), "w", encoding="utf-8") as f:
            f.write(output_report(all_jobs))
        log.info("日报: %s/招聘日报_%s.md", out_dir, DATE_STR)

        # CSV 格式，方便 Excel 打开
        csv_path = out_dir / ("招聘数据_%s.csv" % DATE_STR)
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "title",
                    "company",
                    "salary",
                    "city",
                    "experience",
                    "education",
                    "hr_name",
                    "hr_title",
                    "url",
                    "description",
                ],
            )
            writer.writeheader()
            for j in all_jobs:
                writer.writerow({k: j.get(k, "") for k in writer.fieldnames})
        log.info("数据: %s/招聘数据_%s.csv", out_dir, DATE_STR)
        log.info("完成")

    finally:
        sc.close()


if __name__ == "__main__":
    main()
