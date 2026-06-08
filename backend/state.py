#!/usr/bin/env python3
"""
SQLite 数据层 —— 投递记录、聊天消息、设置、每日统计。
"""

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent.parent / ".boss_profile" / "boss_state.db"

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
            city TEXT,                                      -- 城市，如"淄博"
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
    # 默认设置
    defaults = {
        "greeting_template": "您好！看到贵司在招{job_title}，很感兴趣。PS：正在和你聊天的这个AI工具是我自己开发的——就当是我的技术名片了",
        "greeting_enabled": "true",
        "ai_reply_style": "professional",
        "daily_apply_limit": "15",
        "auto_reply_enabled": "true",
        "min_reply_delay_sec": "15",
        "max_reply_delay_sec": "20",
        "batch_delay_min_sec": "30",
        "batch_delay_max_sec": "90",
        "resume_summary": "",
        "wechat_id": "",
        "search_keywords": "AI Agent,大模型开发,AI产品经理,RAG开发,大模型应用",
        "scheduler_config": json.dumps({
            "enabled": False,
            "days": [],
            "time_ranges": [],
            "auto_apply": {"keyword": "AI Agent", "city": "淄博", "daily_limit": 30},
            "auto_reply": {"style": "professional"},
        }),
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    db.commit()


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


# ══════════════════════════════════════
#  Conversations
# ══════════════════════════════════════


def get_or_create_conversation(application_id: int, hr_name: str, hr_company: str, job_title: str) -> int:
    db = get_db()
    if application_id:
        row = db.execute("SELECT id FROM conversations WHERE application_id=?", (application_id,)).fetchone()
        if row:
            return row["id"]
    # 按 HR 名字查重（精确匹配，去空白）
    name = hr_name.strip() if hr_name else ""
    if name:
        row = db.execute("SELECT id FROM conversations WHERE hr_name=? AND status!='closed'", (name,)).fetchone()
        if row:
            return row["id"]
    cur = db.execute(
        """INSERT INTO conversations (application_id, hr_name, hr_company, job_title)
           VALUES (?, ?, ?, ?)""",
        (application_id, name, hr_company, job_title),
    )
    db.commit()
    return cur.lastrowid


def get_conversation(conv_id: int) -> Optional[dict]:
    return _row_to_dict(get_db().execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone())


def list_active_conversations() -> List[dict]:
    return _rows_to_list(
        get_db().execute("SELECT * FROM conversations WHERE status!='closed' ORDER BY updated_at DESC").fetchall()
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


def replace_conversation_messages(conversation_id: int, messages: List[dict]):
    """用 BOSS 当前消息历史覆盖本地缓存，避免 Web 端展示过期或错会话内容。"""
    db = get_db()
    old_ai = {
        r["content"]
        for r in db.execute(
            "SELECT content FROM messages WHERE conversation_id=? AND ai_generated=1",
            (conversation_id,),
        ).fetchall()
    }
    db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    for msg in messages:
        sender = msg.get("sender", "hr")
        content = (msg.get("content") or "").strip()
        delivery_status = (msg.get("status") or msg.get("delivery_status") or "").strip()
        if not content:
            continue
        ai_generated = 1 if sender == "me" and content in old_ai else 0
        db.execute(
            "INSERT INTO messages (conversation_id, sender, content, delivery_status, ai_generated) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, sender, content, delivery_status, ai_generated),
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


# 启动时初始化
init_db()
