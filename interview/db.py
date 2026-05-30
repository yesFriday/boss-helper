"""
面试问答Agent - 数据库模块
MySQL操作 + 向量存储/检索
"""

import pymysql
import json
from typing import List, Optional, Dict, Any
from llm_client import get_embedding, cosine_similarity

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "wu1364382646",
    "database": "ai_jobs_db",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


def get_conn():
    return pymysql.connect(**DB_CONFIG)


# ========== 面试问答对操作 ==========

def add_qa_pair(category: str, question: str, answer: str,
                difficulty: str = "medium", skills: str = "",
                source_job_id: Optional[int] = None) -> int:
    """添加面试问答对（自动生成embedding）"""
    embedding = get_embedding(question)
    embedding_json = json.dumps(embedding, ensure_ascii=False)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            sql = """INSERT INTO interview_qa_pairs 
                     (category, question, answer, difficulty, embedding, related_skills, source_job_id)
                     VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            cur.execute(sql, (category, question, answer, difficulty, embedding_json, skills, source_job_id))
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def update_qa_embedding(qa_id: int) -> None:
    """更新指定问答对的embedding"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT question FROM interview_qa_pairs WHERE id = %s", (qa_id,))
            row = cur.fetchone()
            if row:
                embedding = get_embedding(row["question"])
                embedding_json = json.dumps(embedding, ensure_ascii=False)
                cur.execute("UPDATE interview_qa_pairs SET embedding = %s WHERE id = %s",
                           (embedding_json, qa_id))
                conn.commit()
    finally:
        conn.close()


def refresh_all_embeddings() -> int:
    """刷新所有问答对的embedding"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, question FROM interview_qa_pairs WHERE embedding IS NULL OR embedding = ''")
            rows = cur.fetchall()
            count = 0
            for row in rows:
                embedding = get_embedding(row["question"])
                embedding_json = json.dumps(embedding, ensure_ascii=False)
                cur.execute("UPDATE interview_qa_pairs SET embedding = %s WHERE id = %s",
                           (embedding_json, row["id"]))
                count += 1
            conn.commit()
            return count
    finally:
        conn.close()


def semantic_search_qa(query: str, category: Optional[str] = None,
                       limit: int = 10) -> List[Dict[str, Any]]:
    """语义搜索最相关的面试题"""
    query_vec = get_embedding(query)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if category:
                cur.execute(
                    "SELECT id, category, question, answer, difficulty, related_skills, embedding "
                    "FROM interview_qa_pairs WHERE embedding IS NOT NULL AND category = %s",
                    (category,)
                )
            else:
                cur.execute(
                    "SELECT id, category, question, answer, difficulty, related_skills, embedding "
                    "FROM interview_qa_pairs WHERE embedding IS NOT NULL"
                )
            rows = cur.fetchall()

        results = []
        for row in rows:
            stored_vec = json.loads(row["embedding"])
            sim = cosine_similarity(query_vec, stored_vec)
            results.append({
                "id": row["id"],
                "category": row["category"],
                "question": row["question"],
                "answer": row["answer"],
                "difficulty": row["difficulty"],
                "skills": row["related_skills"],
                "similarity": round(sim, 4),
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    finally:
        conn.close()


# ========== 岗位JD操作 ==========

def search_jobs_by_semantic(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """语义搜索匹配的岗位"""
    query_vec = get_embedding(query)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, salary, company, experience, education, "
                "requirement_category, requirement_text, source_url "
                "FROM job_requirements"
            )
            rows = cur.fetchall()

        results = []
        for row in rows:
            # 用title+requirement_text算相似度
            text = f"{row['title']} {row['requirement_category'] or ''} {row['requirement_text'] or ''}"
            text_vec = get_embedding(text[:500])  # 截取前500字符
            sim = cosine_similarity(query_vec, text_vec)
            results.append({
                "id": row["id"],
                "title": row["title"],
                "salary": row["salary"],
                "company": row["company"],
                "experience": row["experience"],
                "education": row["education"],
                "category": row["requirement_category"],
                "description": (row["requirement_text"] or "")[:200],
                "url": row["source_url"],
                "similarity": round(sim, 4),
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    finally:
        conn.close()


def get_all_job_categories() -> List[str]:
    """获取所有岗位分类"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT requirement_category FROM job_requirements WHERE requirement_category IS NOT NULL")
            return [r["requirement_category"] for r in cur.fetchall()]
    finally:
        conn.close()


# ========== 面试记录操作 ==========

def save_interview_record(session_id: str, question_id: Optional[int],
                          question: str, user_answer: str,
                          score: float, feedback: str,
                          job_focus: str = "") -> int:
    """保存面试记录"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            sql = """INSERT INTO interview_records 
                     (session_id, question_id, question, user_answer, score, feedback, job_focus)
                     VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            cur.execute(sql, (session_id, question_id, question, user_answer,
                             round(score, 1), feedback, job_focus))
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_session_summary(session_id: str) -> Dict[str, Any]:
    """获取一次面试的总结"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as total, AVG(score) as avg_score, "
                "MIN(score) as min_score, MAX(score) as max_score "
                "FROM interview_records WHERE session_id = %s",
                (session_id,)
            )
            stats = cur.fetchone()

            cur.execute(
                "SELECT question, user_answer, score, feedback, created_at "
                "FROM interview_records WHERE session_id = %s ORDER BY created_at",
                (session_id,)
            )
            records = cur.fetchall()

        return {
            "session_id": session_id,
            "total_questions": stats["total"],
            "avg_score": round(float(stats["avg_score"] or 0), 1),
            "min_score": float(stats["min_score"] or 0),
            "max_score": float(stats["max_score"] or 0),
            "records": records,
        }
    finally:
        conn.close()


def get_weak_areas(limit: int = 10) -> List[Dict[str, Any]]:
    """分析薄弱环节（得分最低的题目）"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT question, user_answer, score, feedback, job_focus, created_at "
                "FROM interview_records "
                "WHERE score IS NOT NULL "
                "ORDER BY score ASC LIMIT %s",
                (limit,)
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_all_session_ids() -> List[str]:
    """获取所有会话ID"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT session_id, MIN(created_at) as first_time "
                "FROM interview_records GROUP BY session_id ORDER BY first_time DESC"
            )
            return [r["session_id"] for r in cur.fetchall()]
    finally:
        conn.close()
