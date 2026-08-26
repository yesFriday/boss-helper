#!/usr/bin/env python3
"""
SQLite 数据层 —— 投递记录、聊天消息、设置、每日统计。
"""

import json
import sqlite3
import threading
from datetime import date, datetime

from backend.logger import get_logger
from backend.path_config import get_boss_data_dir

log = get_logger("state")

DB_PATH = get_boss_data_dir() / "boss_state.db"

_local = threading.local()


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    db = get_db()
    db.executescript("""
        -- 岗位/投递记录表：每投递一个岗位生成一条记录
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,          -- 主键ID
            job_title TEXT NOT NULL,                        -- 岗位名称，如"AI Agent开发"
            company TEXT,                                   -- 公司名称
            salary TEXT,                                    -- 薪资范围，如"15-25K"
            job_url TEXT UNIQUE NOT NULL,                   -- 岗位详情页URL（唯一）
            city TEXT,                                      -- 城市，如"广州"
            experience TEXT,                                -- 经验要求，如"3-5年"
            education TEXT,                                 -- 学历要求，如"本科"
            hr_name TEXT,                                   -- HR姓名
            hr_title TEXT,                                  -- HR职位，如"招聘经理"
            hr_active_time TEXT,                            -- HR活跃时间，如"刚刚活跃"、"在线"
            description TEXT,                               -- 岗位描述/JD全文
            status TEXT DEFAULT 'pending',                  -- 状态：pending=待投递, applied=已投递, skipped=已跳过
            greeting_text TEXT,                             -- 发送的招呼语内容
            greeting_sent_at TIMESTAMP,                     -- 招呼语发送时间
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 最后更新时间
        );

        -- 会话表：每个HR的对话记录（一个HR一条记录）
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,          -- 主键ID
            application_id INTEGER REFERENCES applications(id), -- 关联的岗位ID
            hr_name TEXT NOT NULL,                          -- HR姓名
            hr_company TEXT,                                -- HR所在公司
            job_title TEXT,                                 -- 应聘岗位名称
            last_message_text TEXT,                         -- 最后一条消息内容
            last_message_from TEXT,                         -- 最后消息发送者：hr/me
            last_message_at TIMESTAMP,                      -- 最后消息时间
            unread_count INTEGER DEFAULT 0,                 -- 未读消息数
            status TEXT DEFAULT 'active',                   -- 会话状态：active=活跃, closed=已结束
            auto_reply_enabled INTEGER DEFAULT 1,           -- 是否开启自动回复：1=开启, 0=关闭
            interest_level TEXT,                            -- HR兴趣度：high/medium/low（AI评估）
            hr_wechat TEXT,                                 -- HR的微信号（从聊天中提取）
            wechat_shared_at TIMESTAMP,                     -- 微信交换时间
            resume_sent INTEGER DEFAULT 0,                  -- 是否已发送简历：1=已发送, 0=未发送
            phone_shared INTEGER DEFAULT 0,                 -- 是否已交换电话：1=已交换, 0=未交换
            is_dangerous INTEGER DEFAULT 0,                 -- 是否风险会话：1=已被HR怀疑是AI, 0=正常
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 最后更新时间
        );

        -- 消息表：每条聊天消息（一个会话有多条消息）
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,          -- 主键ID
            conversation_id INTEGER NOT NULL REFERENCES conversations(id), -- 所属会话ID
            sender TEXT NOT NULL,                           -- 发送者：hr=HR发送, me=我方发送
            content TEXT NOT NULL,                          -- 消息内容
            delivery_status TEXT,                           -- 送达状态：已读/未读/送达/发送失败
            ai_generated INTEGER DEFAULT 0,                 -- 是否AI生成：1=AI生成, 0=人工发送
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 消息时间
        );

        -- 配置表：系统配置项（键值对存储）
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,                           -- 配置项名称
            value TEXT NOT NULL,                            -- 配置项值（JSON字符串）
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 最后更新时间
        );

        -- 每日统计表：每天的投递和聊天统计
        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,                          -- 日期，如"2026-06-01"
            applications_sent INTEGER DEFAULT 0,            -- 当日投递数
            messages_sent INTEGER DEFAULT 0,                -- 当日发送消息数
            messages_received INTEGER DEFAULT 0,            -- 当日接收消息数
            auto_replies_sent INTEGER DEFAULT 0             -- 当日AI自动回复数
        );
    """)
    try:
        db.execute("ALTER TABLE messages ADD COLUMN delivery_status TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN interest_level TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN hr_wechat TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN wechat_shared_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN resume_sent INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN phone_shared INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE applications ADD COLUMN hr_active_time TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN summary TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN summary_upto_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # 会话身份主键：BOSS securityId（同名不同 HR 也能区分）
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN security_id TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS idx_conversations_security_id ON conversations(security_id)")
    except sqlite3.OperationalError:
        pass
    # 工具事件表：Agent 有副作用的工具调用记录（发简历/换微信/约面试等），供后续轮次上下文回溯
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tool_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id),
            tool_name       TEXT NOT NULL,
            result_summary  TEXT NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 候选池表
    db.executescript("""
        CREATE TABLE IF NOT EXISTS shortlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_url TEXT UNIQUE NOT NULL,
            job_title TEXT NOT NULL,
            company TEXT,
            salary TEXT,
            city TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 面试安排表
    db.executescript("""
        CREATE TABLE IF NOT EXISTS interviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            company         TEXT    NOT NULL,
            job_title       TEXT    NOT NULL,
            interview_type  TEXT    NOT NULL DEFAULT 'online',
            interview_date  TEXT    NOT NULL,
            start_time      TEXT    NOT NULL,
            end_time        TEXT    NOT NULL,
            duration_min    INTEGER NOT NULL DEFAULT 60,
            location        TEXT,
            lat             REAL,
            lng             REAL,
            contact_name    TEXT,
            contact_phone   TEXT,
            status          TEXT    NOT NULL DEFAULT 'pending',
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 默认设置
    defaults = {
        "greeting_template": "你好，贵司{job_title}还在招人吗？想发份简历给您看下，方便吗？",
        "greeting_enabled": "true",
        "ai_reply_style": "professional",
        "daily_apply_limit": "15",
        "auto_reply_enabled": "true",
        "min_reply_delay_sec": "15",
        "max_reply_delay_sec": "20",
        "batch_delay_min_sec": "3",
        "batch_delay_max_sec": "8",
        "resume_summary": "",
        "wechat_id": "",
        "search_keywords": "AI Agent,大模型开发,AI产品经理,RAG开发,大模型应用",
        "scheduler_config": json.dumps({
            "enabled": False,
            "days": [],
            "time_ranges": [],
            "auto_apply": {"keyword": "AI Agent", "city": "广州", "daily_limit": 30, "hr_active_filter": "在线,刚刚活跃,今日活跃,3日内活跃,本周活跃,本月活跃"},
            "auto_reply": {"style": "professional"},
        }),
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    db.execute("UPDATE settings SET value='3' WHERE key='batch_delay_min_sec' AND value='30'")
    db.execute("UPDATE settings SET value='8' WHERE key='batch_delay_max_sec' AND value='90'")
    db.commit()
    # 迁移：为已有数据库添加 is_dangerous 字段
    try:
        db.execute("ALTER TABLE conversations ADD COLUMN is_dangerous INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _row_to_dict(row) -> Optional[dict]:
    return dict(row) if row else None


def _rows_to_list(rows) -> List[dict]:
    return [dict(r) for r in rows]


# ══════════════════════════════════════
#  Applications
# ══════════════════════════════════════


def add_application(job: dict) -> int:
    db = get_db()
    cur = db.execute(
        """INSERT OR IGNORE INTO applications
           (job_title, company, salary, job_url, city, experience, education, hr_name, hr_title, hr_active_time, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            job.get("title", ""),
            job.get("company", ""),
            job.get("salary", ""),
            job.get("url", ""),
            job.get("city", ""),
            job.get("experience", ""),
            job.get("education", ""),
            job.get("hr_name", ""),
            job.get("hr_title", ""),
            job.get("hr_active_time", ""),
            job.get("description", ""),
        ),
    )
    db.commit()
    return cur.lastrowid if cur.lastrowid else 0


def get_application(app_id: int) -> Optional[dict]:
    return _row_to_dict(get_db().execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone())


def get_application_by_url(url: str) -> Optional[dict]:
    return _row_to_dict(get_db().execute("SELECT * FROM applications WHERE job_url=?", (url,)).fetchone())


def update_application_from_job(app_id: int, job: dict) -> Optional[dict]:
    """用本次搜索结果刷新已有岗位；空值不覆盖旧值。"""
    fields = {
        "job_title": job.get("title", ""),
        "company": job.get("company", ""),
        "salary": job.get("salary", ""),
        "city": job.get("city", ""),
        "experience": job.get("experience", ""),
        "education": job.get("education", ""),
        "hr_name": job.get("hr_name", ""),
        "hr_title": job.get("hr_title", ""),
        "hr_active_time": job.get("hr_active_time", ""),
        "description": job.get("description", ""),
    }
    params = []
    assignments = []
    for column, value in fields.items():
        value = (value or "").strip()
        assignments.append(f"{column}=CASE WHEN ?!='' THEN ? ELSE {column} END")
        params.extend([value, value])
    params.append(app_id)

    db = get_db()
    db.execute(
        f"""UPDATE applications SET {", ".join(assignments)},
            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        params,
    )
    db.commit()
    return get_application(app_id)


def list_applications(status: Optional[str] = None, limit: int = 50) -> List[dict]:
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM applications WHERE status=? ORDER BY updated_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM applications ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return _rows_to_list(rows)


def update_application_status(app_id: int, status: str, greeting_text: Optional[str] = None):
    db = get_db()
    if greeting_text:
        db.execute(
            """UPDATE applications SET status=?, greeting_text=?, greeting_sent_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (status, greeting_text, app_id),
        )
    else:
        db.execute(
            "UPDATE applications SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, app_id),
        )
    db.commit()


def get_today_application_count() -> int:
    row = (
        get_db()
        .execute("SELECT COUNT(*) as cnt FROM applications WHERE status='applied' AND date(updated_at)=date('now','localtime')")
        .fetchone()
    )
    return row["cnt"] if row else 0


def get_today_pending_count() -> int:
    row = get_db().execute("SELECT COUNT(*) as cnt FROM applications WHERE status='pending'").fetchone()
    return row["cnt"] if row else 0


def count_hours_replied_in_range(hours: int) -> int:
    row = (
        get_db()
        .execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE last_message_from='hr' AND datetime(last_message_at) > datetime('now','localtime',? || ' hours')",
            (f"-{hours}",),
        )
        .fetchone()
    )
    return row["cnt"] if row else 0


def count_interest_level(level: str) -> int:
    row = get_db().execute("SELECT COUNT(*) as cnt FROM conversations WHERE interest_level=?", (level,)).fetchone()
    return row["cnt"] if row else 0


def get_pending_applications(limit: int = 50) -> List[dict]:
    return _rows_to_list(
        get_db()
        .execute(
            "SELECT * FROM applications WHERE status='pending' AND job_url!='' ORDER BY id LIMIT ?",
            (limit,),
        )
        .fetchall()
    )


def get_pending_applications_by_activity(
    limit: int = 50, hr_active_filter: str = "all"
) -> List[dict]:
    """
    按 HR 活跃度优先级排序获取待投岗位。
    hr_active_filter:
      - "all" / ""  → 所有待投岗位（按活跃度排序）
      - "online"     → 只看在线/刚刚活跃/今日活跃的（兼容旧版）
      - "recent"     → 只看在线/刚刚活跃/今日活跃/本周活跃的（兼容旧版）
      - "在线,刚刚活跃" → 逗号分隔列表，只看列出的状态
    """
    db = get_db()

    # 活跃度优先级：在线 > 刚刚活跃 > 今日活跃 > 本周活跃 > 本月活跃 > 其他
    if hr_active_filter == "online":
        rows = db.execute(
            """SELECT * FROM applications
               WHERE status='pending' AND job_url!=''
                 AND hr_active_time IN ('在线', '刚刚活跃', '今日活跃')
               ORDER BY
                 CASE hr_active_time
                   WHEN '在线' THEN 0
                   WHEN '刚刚活跃' THEN 1
                   WHEN '今日活跃' THEN 2
                   ELSE 3
                 END, id
               LIMIT ?""",
            (limit,),
        ).fetchall()
    elif hr_active_filter == "recent":
        rows = db.execute(
            """SELECT * FROM applications
               WHERE status='pending' AND job_url!=''
                 AND hr_active_time IN ('在线', '刚刚活跃', '今日活跃', '本周活跃')
               ORDER BY
                 CASE hr_active_time
                   WHEN '在线' THEN 0
                   WHEN '刚刚活跃' THEN 1
                   WHEN '今日活跃' THEN 2
                   WHEN '本周活跃' THEN 3
                   ELSE 4
                 END, id
               LIMIT ?""",
            (limit,),
        ).fetchall()
    elif hr_active_filter and hr_active_filter not in ("all", ""):
        # 逗号分隔列表，如 "在线,刚刚活跃,今日活跃"
        statuses = [s.strip() for s in hr_active_filter.split(",") if s.strip()]
        if statuses:
            placeholders = ",".join(["?"] * len(statuses))
            rows = db.execute(
                f"""SELECT * FROM applications
                   WHERE status='pending' AND job_url!=''
                     AND hr_active_time IN ({placeholders})
                   ORDER BY
                     CASE hr_active_time
                       WHEN '在线' THEN 0
                       WHEN '刚刚活跃' THEN 1
                       WHEN '今日活跃' THEN 2
                       WHEN '3日内活跃' THEN 3
                       WHEN '本周活跃' THEN 4
                       WHEN '本月活跃' THEN 5
                       ELSE 6
                     END, id
                   LIMIT ?""",
                (*statuses, limit),
            ).fetchall()
        else:
            rows = []
    else:  # "all" — 全部按活跃度排序，活跃度高的优先
        rows = db.execute(
            """SELECT * FROM applications
               WHERE status='pending' AND job_url!=''
               ORDER BY
                 CASE
                   WHEN hr_active_time IS NULL OR hr_active_time = '' THEN 99
                   WHEN hr_active_time = '在线' THEN 0
                   WHEN hr_active_time = '刚刚活跃' THEN 1
                   WHEN hr_active_time = '今日活跃' THEN 2
                   WHEN hr_active_time = '本周活跃' THEN 3
                   WHEN hr_active_time = '本月活跃' THEN 4
                   ELSE 5
                 END, id
               LIMIT ?""",
            (limit,),
        ).fetchall()

    return _rows_to_list(rows)


# ══════════════════════════════════════
#  Conversations
# ══════════════════════════════════════


def get_or_create_conversation(
    application_id: int, hr_name: str, hr_company: str, job_title: str, security_id: str = ""
) -> int:
    db = get_db()
    # securityId 精确归并（会话身份主键，同名不同 HR 也能区分）
    sid = (security_id or "").strip()
    if sid:
        row = db.execute(
            "SELECT id FROM conversations WHERE security_id=? AND status!='closed'", (sid,)
        ).fetchone()
        if row:
            # 名字以更精确的提取值为准
            name = hr_name.strip() if hr_name else ""
            if name:
                db.execute("UPDATE conversations SET hr_name=? WHERE id=? AND hr_name!=?", (name, row["id"], name))
                db.commit()
            return row["id"]
    if application_id:
        row = db.execute("SELECT id FROM conversations WHERE application_id=?", (application_id,)).fetchone()
        if row:
            if sid:
                db.execute("UPDATE conversations SET security_id=? WHERE id=?", (sid, row["id"]))
                db.commit()
            return row["id"]
    # 按 HR 名字查重（精确匹配，去空白）；有 securityId 的名字撞车不归并（可能同名不同人）
    name = hr_name.strip() if hr_name else ""
    if name and not sid:
        row = db.execute("SELECT id FROM conversations WHERE hr_name=? AND status!='closed'", (name,)).fetchone()
        if row:
            return row["id"]
    cur = db.execute(
        """INSERT INTO conversations (application_id, hr_name, hr_company, job_title, security_id)
           VALUES (?, ?, ?, ?, ?)""",
        (application_id, name, hr_company, job_title, sid or None),
    )
    db.commit()
    return cur.lastrowid


def get_conversation_by_security_id(security_id: str) -> Optional[dict]:
    if not security_id:
        return None
    return _row_to_dict(
        get_db()
        .execute("SELECT * FROM conversations WHERE security_id=?", (security_id,))
        .fetchone()
    )


def update_conversation_security_id(conversation_id: int, security_id: str):
    """学习/修正会话的 securityId（存量会话首次打开时回填）。"""
    if not security_id:
        return
    get_db().execute(
        "UPDATE conversations SET security_id=? WHERE id=? AND (security_id IS NULL OR security_id='')",
        (security_id, conversation_id),
    )
    get_db().commit()


def get_conversation(conv_id: int) -> Optional[dict]:
    return _row_to_dict(get_db().execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone())


def list_active_conversations(dangerous_only: bool = False) -> List[dict]:
    if dangerous_only:
        return _rows_to_list(
            get_db().execute(
                "SELECT * FROM conversations WHERE is_dangerous=1 ORDER BY updated_at DESC"
            ).fetchall()
        )
    return _rows_to_list(
        get_db().execute(
            "SELECT * FROM conversations WHERE status!='closed' AND is_dangerous=0 ORDER BY updated_at DESC"
        ).fetchall()
    )


def get_stale_hr_conversations(minutes: int = 10, limit: int = 2) -> List[dict]:
    """孤儿消息兜底扫描：最后一条是 HR 消息且超过 N 分钟未回复的活跃会话。

    未读红点一旦被打开即消失，回复失败的消息会"已读未回"且永不再试；
    本查询从 DB 侧兜底找回这些会话。last_message_at 以 CURRENT_TIMESTAMP(UTC) 存储，
    与 datetime('now') 同基准。
    """
    return _rows_to_list(
        get_db()
        .execute(
            """SELECT * FROM conversations
               WHERE status='active' AND auto_reply_enabled=1 AND is_dangerous=0
                 AND last_message_from='hr'
                 AND last_message_at < datetime('now', ?)
               ORDER BY last_message_at ASC LIMIT ?""",
            (f"-{int(minutes)} minutes", limit),
        )
        .fetchall()
    )


def find_conversation_by_hr_name(hr_name: str) -> Optional[dict]:
    return _row_to_dict(
        get_db()
        .execute(
            "SELECT * FROM conversations WHERE hr_name=? ORDER BY updated_at DESC LIMIT 1",
            (hr_name,),
        )
        .fetchone()
    )


def update_conversation_last_message(conv_id: int, text: str, sender: str, unread_delta: int = 0):
    db = get_db()
    db.execute(
        """UPDATE conversations SET last_message_text=?, last_message_from=?,
           last_message_at=CURRENT_TIMESTAMP, unread_count=MAX(0, unread_count+?),
           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (text[:200], sender, unread_delta, conv_id),
    )
    db.commit()


def update_conversation_status(conv_id: int, status: str):
    get_db().execute(
        "UPDATE conversations SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, conv_id),
    )
    get_db().commit()


def update_conversation_interest(conv_id: int, level: str):
    get_db().execute(
        "UPDATE conversations SET interest_level=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (level, conv_id),
    )
    get_db().commit()


def update_conversation_wechat(conv_id: int, wechat_id: str):
    get_db().execute(
        "UPDATE conversations SET hr_wechat=?, wechat_shared_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (wechat_id, conv_id),
    )
    get_db().commit()


def mark_resume_sent(conv_id: int):
    get_db().execute("UPDATE conversations SET resume_sent=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (conv_id,))
    get_db().commit()


def mark_phone_shared(conv_id: int):
    get_db().execute("UPDATE conversations SET phone_shared=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (conv_id,))
    get_db().commit()


def mark_conversation_dangerous(conv_id: int):
    """标记会话为风险会话（HR怀疑是AI），后续不再进行AI监听和自动回复。"""
    get_db().execute(
        "UPDATE conversations SET is_dangerous=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (conv_id,),
    )
    get_db().commit()


def get_wechat_exchanges() -> List[dict]:
    """返回所有已获取到微信号的会话，包含岗位详情。"""
    return _rows_to_list(
        get_db()
        .execute(
            """SELECT c.id, c.hr_name, c.hr_company, c.job_title, c.hr_wechat,
                      c.wechat_shared_at, c.interest_level,
                      a.city, a.salary, a.experience, a.education, a.description
               FROM conversations c
               LEFT JOIN applications a ON c.application_id = a.id
               WHERE c.hr_wechat IS NOT NULL AND c.hr_wechat != ''
               ORDER BY c.wechat_shared_at DESC"""
        )
        .fetchall()
    )


def set_auto_reply(conv_id: int, enabled: bool):
    get_db().execute(
        "UPDATE conversations SET auto_reply_enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (1 if enabled else 0, conv_id),
    )
    get_db().commit()


# ══════════════════════════════════════
#  Messages
# ══════════════════════════════════════


def add_message(
    conversation_id: int, sender: str, content: str, ai_generated: bool = False, delivery_status: str = ""
) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO messages (conversation_id, sender, content, delivery_status, ai_generated) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, sender, content, delivery_status, 1 if ai_generated else 0),
    )
    db.commit()
    return cur.lastrowid


def get_messages(conversation_id: int, limit: int = 50) -> List[dict]:
    return _rows_to_list(
        get_db()
        .execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC, id ASC LIMIT ?",
            (conversation_id, limit),
        )
        .fetchall()
    )


def get_recent_messages(conversation_id: int, limit: int = 5) -> List[dict]:
    return _rows_to_list(
        get_db()
        .execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (conversation_id, limit),
        )
        .fetchall()
    )


def get_all_messages(conversation_id: int) -> List[dict]:
    """获取该会话的所有消息记录，按时间正序排列。"""
    return _rows_to_list(
        get_db()
        .execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC, id ASC",
            (conversation_id,),
        )
        .fetchall()
    )


def replace_conversation_messages(conversation_id: int, messages: List[dict]):
    """增量同步：用 BOSS 当前可见消息历史对齐并增量更新本地缓存，保留完整历史消息。"""
    db = get_db()
    
    # 1. 获取数据库中已有的该会话所有消息记录，按时间正序
    db_msgs = _rows_to_list(db.execute(
        "SELECT id, sender, content, delivery_status, ai_generated FROM messages WHERE conversation_id=? ORDER BY id ASC",
        (conversation_id,)
    ).fetchall())
    
    if not messages:
        return
        
    # 2. 构建网页读取的消息对象列表，清除内容首尾空白
    clean_web_msgs = []
    for msg in messages:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        clean_web_msgs.append({
            "sender": msg.get("sender", "hr"),
            "content": content,
            "status": (msg.get("status") or msg.get("delivery_status") or "").strip()
        })
        
    if not clean_web_msgs:
        return

    # 3. 寻找最大重叠区（滑动窗口比对）
    k = len(db_msgs)
    m = len(clean_web_msgs)
    overlap_len = 0
    
    for l in range(min(k, m), 0, -1):
        match = True
        for idx in range(l):
            db_item = db_msgs[k - l + idx]
            web_item = clean_web_msgs[idx]
            if db_item["sender"] != web_item["sender"] or db_item["content"] != web_item["content"]:
                match = False
                break
        if match:
            overlap_len = l
            break

    # 4. 更新重叠区的消息状态，并确定需要新插入的消息
    if overlap_len > 0:
        for idx in range(overlap_len):
            db_item = db_msgs[k - overlap_len + idx]
            web_item = clean_web_msgs[idx]
            new_status = web_item["status"]
            if new_status and db_item["delivery_status"] != new_status:
                db.execute(
                    "UPDATE messages SET delivery_status=? WHERE id=?",
                    (new_status, db_item["id"])
                )
        new_msgs_to_insert = clean_web_msgs[overlap_len:]
    else:
        # 无重叠区：可能是库为空（正常追加），也可能是滑动窗口失配（渲染差异/过滤规则变化
        # 导致内容不再逐字相等）。集合去重兜底：跳过 DB 最近 100 条中已存在的 (sender, content)，
        # 防止整段历史重复追加污染上下文；滑动窗口正常命中时不会走到这里。
        if db_msgs:
            recent_keys = {(m["sender"], m["content"]) for m in db_msgs[-100:]}
            deduped = [m for m in clean_web_msgs if (m["sender"], m["content"]) not in recent_keys]
            skipped = len(clean_web_msgs) - len(deduped)
            if skipped:
                log.warning(
                    f"[state] 会话{conversation_id} 滑动窗口失配，集合去重跳过 {skipped} 条疑似重复消息"
                )
            new_msgs_to_insert = deduped
        else:
            new_msgs_to_insert = clean_web_msgs

    # 5. 获取已有的 AI 生成回复内容，做标记保留（对新插入的进行识别）
    old_ai = {
        r["content"]
        for r in db.execute(
            "SELECT content FROM messages WHERE conversation_id=? AND ai_generated=1",
            (conversation_id,),
        ).fetchall()
    }

    # 6. 插入新消息
    for msg in new_msgs_to_insert:
        sender = msg["sender"]
        content = msg["content"]
        status = msg["status"]
        ai_generated = 1 if sender == "me" and content in old_ai else 0
        db.execute(
            "INSERT INTO messages (conversation_id, sender, content, delivery_status, ai_generated) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, sender, content, status, ai_generated),
        )

    # 7. 反向已读推导逻辑：如果同步时最新的一条消息是 HR 发送的，直接将我方所有历史消息标记为“已读”
    if clean_web_msgs[-1]["sender"] == "hr":
        db.execute(
            "UPDATE messages SET delivery_status='已读' WHERE conversation_id=? AND sender='me' AND delivery_status != '已读'",
            (conversation_id,)
        )

    db.commit()


def get_last_hr_message(conversation_id: int) -> Optional[dict]:
    return _row_to_dict(
        get_db()
        .execute(
            "SELECT * FROM messages WHERE conversation_id=? AND sender='hr' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        )
        .fetchone()
    )


def message_exists(conversation_id: int, content: str, sender: str) -> bool:
    row = (
        get_db()
        .execute(
            "SELECT id FROM messages WHERE conversation_id=? AND content=? AND sender=? ORDER BY created_at DESC LIMIT 1",
            (conversation_id, content, sender),
        )
        .fetchone()
    )
    return row is not None


# ══════════════════════════════════════
#  工具事件 / 会话摘要 / 岗位回填
# ══════════════════════════════════════


def record_tool_event(conversation_id: int, tool_name: str, result_summary: str):
    """记录一次有副作用的 Agent 工具调用，供后续轮次上下文回溯。"""
    if not result_summary:
        return
    get_db().execute(
        "INSERT INTO tool_events (conversation_id, tool_name, result_summary) VALUES (?, ?, ?)",
        (conversation_id, tool_name, result_summary[:200]),
    )
    get_db().commit()


def get_recent_tool_events(conversation_id: int, limit: int = 5) -> List[dict]:
    """最近的工具事件，按时间倒序。"""
    return _rows_to_list(
        get_db()
        .execute(
            "SELECT tool_name, result_summary, created_at FROM tool_events "
            "WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        )
        .fetchall()
    )


def update_conversation_summary(conversation_id: int, summary: str, upto_message_id: int):
    """写入/滚动更新会话长历史摘要。upto_message_id 表示摘要已覆盖到的消息 id。"""
    get_db().execute(
        "UPDATE conversations SET summary=?, summary_upto_id=? WHERE id=?",
        (summary, upto_message_id, conversation_id),
    )
    get_db().commit()


def get_conversation_summary(conversation_id: int) -> tuple:
    """返回 (summary, summary_upto_id)。"""
    row = get_db().execute(
        "SELECT summary, summary_upto_id FROM conversations WHERE id=?", (conversation_id,)
    ).fetchone()
    if not row:
        return "", 0
    return (row["summary"] or ""), (row["summary_upto_id"] or 0)


def get_application_by_hr_name(hr_name: str) -> Optional[dict]:
    """按 HR 名字反查投递记录，回填聊天会话缺失的岗位信息。取最新一条。"""
    if not hr_name:
        return None
    rows = _rows_to_list(
        get_db()
        .execute(
            "SELECT * FROM applications WHERE hr_name=? ORDER BY id DESC LIMIT 1",
            (hr_name,),
        )
        .fetchall()
    )
    return rows[0] if rows else None


# BOSS 平台系统通知前缀（≤80字且以此开头 → 非HR真实消息，不存库、不进上下文）
SYSTEM_NOTIFICATION_PREFIXES = (
    "你与该职位竞争者PK情况",
    "竞争力分析",
    "BOSS安全提示",
    "系统消息",
    "沟通分析",
    "今日推荐",
    "该Boss已查看了你的简历",
)


def is_system_notification(content: str) -> bool:
    """判断一条消息是否为 BOSS 系统通知（短文本且以已知系统前缀开头）。"""
    content = (content or "").strip()
    if len(content) > 80:
        return False
    return any(content.startswith(p) for p in SYSTEM_NOTIFICATION_PREFIXES)


def purge_system_notifications() -> int:
    """清理历史存库的系统通知消息（一次性迁移，幂等）。返回删除条数。"""
    rows = _rows_to_list(
        get_db()
        .execute(
            "SELECT id, content FROM messages WHERE sender='hr' AND length(content) <= 80"
        )
        .fetchall()
    )
    ids = [r["id"] for r in rows if is_system_notification(r["content"])]
    if not ids:
        return 0
    db = get_db()
    db.executemany("DELETE FROM messages WHERE id=?", [(i,) for i in ids])
    db.commit()
    log.info(f"[state] 已清理 {len(ids)} 条历史系统通知消息")
    return len(ids)


# ══════════════════════════════════════
#  Settings
# ══════════════════════════════════════


def get_setting(key: str, default: str = "") -> str:
    row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    get_db().execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (key, value),
    )
    get_db().commit()


def get_all_settings() -> dict:
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ══════════════════════════════════════
#  Daily Stats
# ══════════════════════════════════════


def _today() -> str:
    return date.today().isoformat()


def _ensure_today():
    get_db().execute("INSERT OR IGNORE INTO daily_stats (date) VALUES (?)", (_today(),))
    get_db().commit()


def increment_daily_stat(field: str):
    _ensure_today()
    get_db().execute(
        f"UPDATE daily_stats SET {field} = {field} + 1 WHERE date=?",
        (_today(),),
    )
    get_db().commit()


def get_daily_stats(date_str: Optional[str] = None) -> dict:
    d = date_str or _today()
    row = get_db().execute("SELECT * FROM daily_stats WHERE date=?", (d,)).fetchone()
    return dict(row) if row else {}


def get_today_auto_reply_count() -> int:
    row = (
        get_db()
        .execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE ai_generated=1 AND date(created_at)=date('now','localtime')"
        )
        .fetchone()
    )
    return row["cnt"] if row else 0


# ═══════════════════════
#  候选池
# ═══════════════════════
def add_to_shortlist(
    job_url: str, title: str, company: str = "", salary: str = "", city: str = "", note: str = ""
) -> int:
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO shortlists (job_url, job_title, company, salary, city, note) VALUES (?,?,?,?,?,?)",
            (job_url, title, company, salary, city, note),
        )
        db.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return 0


def remove_from_shortlist(shortlist_id: int):
    get_db().execute("DELETE FROM shortlists WHERE id=?", (shortlist_id,))
    get_db().commit()


def list_shortlists(limit: int = 100) -> list:
    rows = get_db().execute("SELECT * FROM shortlists ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return _rows_to_list(rows)


def is_in_shortlist(job_url: str) -> bool:
    row = get_db().execute("SELECT COUNT(*) as cnt FROM shortlists WHERE job_url=?", (job_url,)).fetchone()
    return row["cnt"] > 0 if row else False


# ═══════════════════════
#  面试安排
# ═══════════════════════

def add_interview(
    company: str,
    job_title: str,
    interview_type: str,
    interview_date: str,
    start_time: str,
    end_time: str,
    duration_min: int = 60,
    conversation_id: str = "",
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    contact_name: str = "",
    contact_phone: str = "",
    notes: str = "",
) -> int:
    db = get_db()
    cur = db.execute(
        """INSERT INTO interviews
           (conversation_id, company, job_title, interview_type, interview_date,
            start_time, end_time, duration_min, location, lat, lng,
            contact_name, contact_phone, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (conversation_id, company, job_title, interview_type, interview_date,
         start_time, end_time, duration_min, location, lat, lng,
         contact_name, contact_phone, notes),
    )
    db.commit()
    return cur.lastrowid


def get_interview(interview_id: int) -> Optional[dict]:
    return _row_to_dict(get_db().execute("SELECT * FROM interviews WHERE id=?", (interview_id,)).fetchone())


def list_interviews_by_date(date_str: str) -> List[dict]:
    """查询某天的所有面试（pending + confirmed）"""
    return _rows_to_list(
        get_db().execute(
            """SELECT * FROM interviews
               WHERE interview_date=? AND status IN ('pending','confirmed')
               ORDER BY start_time""",
            (date_str,),
        ).fetchall()
    )


def get_all_upcoming_interviews() -> List[dict]:
    """查询所有未来的面试"""
    return _rows_to_list(
        get_db().execute(
            """SELECT * FROM interviews
               WHERE interview_date >= date('now','localtime')
                 AND status IN ('pending','confirmed')
               ORDER BY interview_date, start_time"""
        ).fetchall()
    )


def get_interviews_by_conversation(conversation_id: str) -> List[dict]:
    """查询某个会话关联的所有面试"""
    return _rows_to_list(
        get_db().execute(
            "SELECT * FROM interviews WHERE conversation_id=? ORDER BY created_at DESC",
            (conversation_id,),
        ).fetchall()
    )


def update_interview_status(interview_id: int, status: str):
    get_db().execute(
        "UPDATE interviews SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, interview_id),
    )
    get_db().commit()


def update_interview(
    interview_id: int,
    interview_date: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    contact_name: Optional[str] = None,
    contact_phone: Optional[str] = None,
    notes: Optional[str] = None,
):
    """部分更新面试信息，传 None 的字段不更新"""
    db = get_db()
    fields = []
    values = []
    for name, val in [
        ("interview_date", interview_date),
        ("start_time", start_time),
        ("end_time", end_time),
        ("location", location),
        ("lat", lat),
        ("lng", lng),
        ("contact_name", contact_name),
        ("contact_phone", contact_phone),
        ("notes", notes),
    ]:
        if val is not None:
            fields.append(f"{name}=?")
            values.append(val)
    if not fields:
        return
    fields.append("updated_at=CURRENT_TIMESTAMP")
    values.append(interview_id)
    db.execute(f"UPDATE interviews SET {', '.join(fields)} WHERE id=?", values)
    db.commit()


def find_available_slots(
    interview_date: str,
    interview_type: str,
    duration_min: int = 60,
) -> List[dict]:
    """
    查询某天可用的面试时段。
    线下：返回上午/下午是否可用（bool），不考虑具体交通时间。
    线上：返回当天所有空隙，间隔至少1小时。
    返回可用时段的列表，每个元素包含 {start_time, end_time, period}。
    """
    existing = list_interviews_by_date(interview_date)

    if interview_type == "offline":
        # 线下规则：上午一场（9:00-12:00），下午一场（14:00-18:00）
        slots = []
        am_occupied = any(_time_overlap(e, ("09:00", "12:00")) for e in existing)
        pm_occupied = any(_time_overlap(e, ("14:00", "18:00")) for e in existing)
        if not am_occupied:
            slots.append({"start_time": "09:00", "end_time": "12:00", "period": "上午"})
        if not pm_occupied:
            slots.append({"start_time": "14:00", "end_time": "18:00", "period": "下午"})
        return slots

    else:
        # 线上规则：找到所有已占用时段，找出中间 ≥ duration_min 且与前后间隔 ≥ 60min 的空隙
        slots = []
        day_start = "08:00"
        day_end = "20:00"

        occupied = [(e["start_time"], e["end_time"]) for e in existing]
        occupied.sort()

        prev_end = day_start
        for s, e in occupied:
            gap = _time_diff_min(prev_end, s)
            if gap >= duration_min + 60:  # 面试时长 + 1小时间隔
                slot_start = prev_end
                slot_end = _add_minutes(slot_start, duration_min)
                if _time_cmp(slot_end, s) < 0:
                    slots.append({"start_time": slot_start, "end_time": slot_end, "period": ""})
            prev_end = max(prev_end, e)

        # 最后一个占用后的空隙
        gap = _time_diff_min(prev_end, day_end)
        if gap >= duration_min:
            slot_start = prev_end
            slot_end = _add_minutes(slot_start, duration_min)
            if _time_cmp(slot_end, day_end) <= 0:
                slots.append({"start_time": slot_start, "end_time": slot_end, "period": ""})

        return slots


# 内部时间工具函数
def _time_to_min(t: str) -> int:
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _time_diff_min(t1: str, t2: str) -> int:
    return _time_to_min(t2) - _time_to_min(t1)


def _add_minutes(t: str, minutes: int) -> str:
    total = _time_to_min(t) + minutes
    h, m = divmod(total % 1440, 60)
    return f"{h:02d}:{m:02d}"


def _time_cmp(t1: str, t2: str) -> int:
    return _time_to_min(t1) - _time_to_min(t2)


def _time_overlap(row: dict, block: tuple) -> bool:
    """判断一个面试的时间是否与某个时间段重叠"""
    rs = row["start_time"]
    re = row["end_time"]
    bs, be = block
    return not (_time_cmp(re, bs) <= 0 or _time_cmp(rs, be) >= 0)


def validate_and_add_interview(conv_id: int, interview_type: str, start_time_str: str, duration_min: int, notes: str = None) -> tuple:
    """
    精密校验并添加面试：
    1. 线下互斥：上午(9:00-12:00)最多1场，下午(14:00-18:00)最多1场。
    2. 间隔时间约束：两场面试（无论是线上还是线下）之间必须有至少 60 分钟缓冲。
    3. 通勤时间追加：如果有任何一方是 offline，间隔时间必须达到 90 分钟。
    """
    from datetime import datetime, timedelta
    
    # 格式化日期和时间
    try:
        # 支持 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS
        start_time_str = start_time_str.strip()
        if len(start_time_str) == 16:
            new_start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        else:
            new_start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return False, f"时间格式解析失败: {e}，请使用 YYYY-MM-DD HH:MM 格式"
        
    new_end = new_start + timedelta(minutes=duration_min)
    interview_date = new_start.strftime("%Y-%m-%d")
    
    db = get_db()
    
    # 规则1: 线下互斥
    if interview_type == "offline":
        # 判定新面试的半天段：上午定义为开始时间在 12:00 之前
        is_morning = new_start.hour < 12
        
        # 查询当天已有的线下安排
        cursor = db.execute(
            "SELECT start_time FROM interviews WHERE interview_date = ? AND interview_type = 'offline'",
            (interview_date,)
        )
        existing_offline = cursor.fetchall()
        for row in existing_offline:
            try:
                ext_time = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    ext_time = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M")
                except Exception:
                    continue
            ext_is_morning = ext_time.hour < 12
            if is_morning == ext_is_morning:
                half_day_str = "上午" if is_morning else "下午"
                return False, f"时间冲突：同半天({half_day_str})已有线下面试安排，不允许再约线下"

    # 查询当天所有已有面试（线上和线下）
    cursor = db.execute(
        "SELECT id, interview_type, start_time, end_time, company, job_title FROM interviews WHERE interview_date = ?",
        (interview_date,)
    )
    existing_all = cursor.fetchall()
    
    for row in existing_all:
        try:
            ext_start = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M:%S")
            ext_end = datetime.strptime(row["end_time"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                ext_start = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M")
                ext_end = datetime.strptime(row["end_time"], "%Y-%m-%d %H:%M")
            except Exception:
                continue
                
        # 判定需要的缓冲距离
        ext_type = row["interview_type"]
        is_any_offline = (interview_type == "offline" or ext_type == "offline")
        required_gap = 90 if is_any_offline else 60
        
        # 判定重合或时间差
        if new_start < ext_end and new_end > ext_start:
            return False, f"时间冲突：与已有面试 {row['company']}-{row['job_title']} ({row['start_time']} 至 {row['end_time']}) 存在重合 overlap！"
            
        if new_start >= ext_end:
            gap = (new_start - ext_end).total_seconds() / 60
            if gap < required_gap:
                gap_type_str = "通勤 + 缓冲" if is_any_offline else "缓冲"
                return False, f"时间冲突：距离前一场面试结束仅隔 {int(gap)} 分钟，不足要求的 {required_gap} 分钟({gap_type_str})"
                
        if ext_start >= new_end:
            gap = (ext_start - new_end).total_seconds() / 60
            if gap < required_gap:
                gap_type_str = "通勤 + 缓冲" if is_any_offline else "缓冲"
                return False, f"时间冲突：距离后一场面试开始仅隔 {int(gap)} 分钟，不足要求的 {required_gap} 分钟({gap_type_str})"

    # 校验通过，写入数据库
    # 获取会话关联的公司和职位信息
    cursor = db.execute(
        "SELECT hr_company, job_title FROM conversations WHERE id = ?",
        (conv_id,)
    )
    conv = cursor.fetchone()
    company = conv["hr_company"] if conv and conv["hr_company"] else "未知公司"
    job_title = conv["job_title"] if conv and conv["job_title"] else "未知岗位"
    
    db.execute(
        """
        INSERT INTO interviews (conversation_id, company, job_title, interview_type, interview_date, start_time, end_time, duration_min, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conv_id,
            company,
            job_title,
            interview_type,
            interview_date,
            new_start.strftime("%Y-%m-%d %H:%M:%S"),
            new_end.strftime("%Y-%m-%d %H:%M:%S"),
            duration_min,
            notes
        )
    )
    db.commit()
    return True, "成功"


def get_upcoming_interviews(days: int = 3) -> list:
    """获取未来几天的所有面试安排列表，用于拼装 Prompt 注入"""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, conversation_id, company, job_title, interview_type, interview_date, start_time, end_time, duration_min, notes
        FROM interviews
        WHERE start_time >= datetime('now', 'localtime')
        ORDER BY start_time ASC
        """
    )
    # 限制筛选天数
    from datetime import datetime, timedelta
    now = datetime.now()
    limit_time = now + timedelta(days=days)
    
    res = []
    for row in cursor.fetchall():
        try:
            st = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                st = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M")
            except Exception:
                st = now
        if st <= limit_time:
            res.append(dict(row))
    return res


def get_all_interviews() -> list:
    """获取所有面试（包括已过去和未来的，按时间倒序）"""
    db = get_db()
    cursor = db.execute(
        """
        SELECT id, conversation_id, company, job_title, interview_type, interview_date, start_time, end_time, duration_min, notes, status
        FROM interviews
        ORDER BY start_time DESC
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def delete_interview(interview_id: int) -> bool:
    """删除面试记录（一键释放时间段）"""
    db = get_db()
    cursor = db.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
    db.commit()
    return cursor.rowcount > 0


# 启动时初始化
init_db()

