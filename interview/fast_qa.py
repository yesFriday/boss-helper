"""
面试问答Agent - 快速检索层（V2）
学习模式：用户提问，系统在2-3秒内给出答案

V2改进：
1. Layer 0.5: 话题分类（关键词+规则，不调LLM，5ms内）
2. 域内检索：限制在分类后的知识域内搜索，避免跨域误配
3. 自动推荐同域相关问题
"""

import json, time, re
from typing import Optional, List, Dict, Any, Tuple
import pymysql
import numpy as np

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

SEMANTIC_MATCH_THRESHOLD = 0.65


# ===== 缓存 =====
class LRUCache:
    def __init__(self, capacity=200):
        self.cache = {}
        self.capacity = capacity
        self.order = []

    def get(self, key):
        if key in self.cache:
            self.order.remove(key)
            self.order.append(key)
            return self.cache[key]
        return None

    def set(self, key, value):
        if key in self.cache:
            self.order.remove(key)
        elif len(self.cache) >= self.capacity:
            oldest = self.order.pop(0)
            del self.cache[oldest]
        self.cache[key] = value
        self.order.append(key)

    def clear(self):
        self.cache.clear()
        self.order.clear()


query_cache = LRUCache(capacity=200)

# ===== Layer 0.5: 话题分类（基于embedding语义匹配） =====

# 每个话题域的代表性描述（用于embedding分类）
TOPIC_DESCRIPTIONS = {
    "Prompt Engineering": "提示词工程 prompt engineering 设计技巧 思维链 few-shot chain-of-thought 角色设定 结构化输出 指令设计",
    "RAG": "RAG 检索增强生成 知识库 向量检索 embedding chunk 分块 重排序 rerank BM25 混合检索 HyDE 知识图谱 GraphRAG CRAG Self-RAG 缓存 文档 多模态 召回率 评估",
    "Agent": "AI Agent 智能体 多智能体 ReAct tool use function calling 记忆 memory 规划 planning LangGraph AutoGen CrewAI MCP 工具调用",
    "大模型": "大模型 LLM Transformer 注意力机制 微调 LoRA 量化 推理加速 训练 预训练 SFT RLHF DPO 模型评估 幻觉",
    "工程化": "工程化 部署 FastAPI Docker 流式输出 监控 日志 CI/CD 限流 安全 容器编排 GPU 成本",
    "Python": "Python 异步 asyncio Pydantic 装饰器 类型提示 协程 生成器",
}

# 关键词辅助（embedding兜底，高置信度关键词覆盖embedding结果）
TOPIC_KEYWORDS = {
    "Prompt Engineering": {
        "keywords": [
            "提示词",
            "prompt",
            "思维链",
            "cot",
            "few-shot",
            "zero-shot",
            "结构化输出",
            "指令设计",
            "角色设定",
            "负向提示",
            "分步指令",
            "提示",
            "prompt engineering",
        ],
        "high_confidence": ["提示词", "prompt engineering", "提示"],
    },
    "RAG": {
        "keywords": [
            "rag",
            "检索增强",
            "chunk",
            "分块",
            "向量检索",
            "向量数据库",
            "rerank",
            "重排序",
            "bm25",
            "混合检索",
            "知识图谱",
            "graph rag",
            "graphrag",
            "cr ag",
            "self-rag",
            "检索质量",
            "文档更新",
            "多模态",
            "召回",
            "query改写",
            "query理解",
            "缓存机制",
            "metadata",
            "长文档",
            "智能客服",
        ],
        "high_confidence": ["rag", "检索增强", "知识图谱", "graph rag"],
    },
    "Agent": {
        "keywords": [
            "agent",
            "智能体",
            "react",
            "multi-agent",
            "多智能体",
            "function calling",
            "tool use",
            "memory",
            "记忆",
            "planning",
            "langgraph",
            "autogen",
            "crewai",
            "mcp",
            "agentic",
        ],
        "high_confidence": ["agent", "智能体", "multi-agent"],
    },
    "大模型": {
        "keywords": [
            "transformer",
            "attention",
            "注意力",
            "llm",
            "大模型",
            "大语言模型",
            "微调",
            "sft",
            "lora",
            "量化",
            "gptq",
            "gguf",
            "推理加速",
            "kv cache",
            "moe",
            "幻觉",
            "temperature",
            "预训练",
        ],
        "high_confidence": ["llm", "大模型", "大语言模型", "transformer"],
    },
    "工程化": {
        "keywords": [
            "fastapi",
            "docker",
            "部署",
            "sse",
            "流式输出",
            "websocket",
            "负载均衡",
            "ci/cd",
            "限流",
            "提示注入",
            "容器编排",
            "gpu",
        ],
        "high_confidence": ["docker", "部署", "fastapi"],
    },
    "Python": {
        "keywords": ["python", "asyncio", "异步", "pydantic", "装饰器", "生成器"],
        "high_confidence": ["python"],
    },
}


def classify_topic(question: str) -> Optional[str]:
    """对用户问题做话题分类，返回最匹配的话题域（纯关键词为主，embedding兜底）"""
    q_lower = question.lower()

    # 1. 关键词匹配（主方案，更快更准）
    kw_scores = {}
    for topic, info in TOPIC_KEYWORDS.items():
        score = 0
        for kw in info["keywords"]:
            if kw in q_lower:
                score += 1
        for kw in info.get("high_confidence", []):
            if kw in q_lower:
                score += 3
        if score > 0:
            kw_scores[topic] = score

    # 高置信度关键词命中 → 直接返回
    for topic, score in kw_scores.items():
        if score >= 3:
            return topic

    # 单个关键词命中 → 返回得分最高的
    if kw_scores:
        kw_best = max(kw_scores, key=kw_scores.get)
        if kw_scores[kw_best] >= 1:
            return kw_best

    # 2. embedding兜底：关键词没命中时用语义判断
    if not hasattr(classify_topic, "_desc_vecs"):
        classify_topic._desc_vecs = {}
    desc_vecs = classify_topic._desc_vecs

    query_vec = get_embedding(question)
    best_topic, best_score = None, 0
    for topic, desc in TOPIC_DESCRIPTIONS.items():
        if topic not in desc_vecs:
            desc_vecs[topic] = get_embedding(desc)
        sim = cosine_similarity(query_vec, desc_vecs[topic])
        if sim > best_score:
            best_score, best_topic = sim, topic

    return best_topic if best_score >= 0.35 else None


# ===== 域内检索 =====


def _domain_filter_sql(topic: Optional[str]) -> Tuple[str, list]:
    """生成按话题域过滤的SQL条件"""
    if topic:
        # 标准化topic映射到数据库里的category
        topic_to_category = {
            "RAG": "RAG",
            "Agent": "Agent",
            "大模型": "大模型",
            "工程化": "工程化",
            "Python": "Python",
            "Prompt Engineering": "大模型",  # prompt题归在大模型类
        }
        category = topic_to_category.get(topic)
        if category:
            return "AND category = %s", [category]
    return "", []


def _load_qa_in_domain(topic: Optional[str]) -> List[Dict]:
    """加载指定域的所有问答对"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            filter_sql, params = _domain_filter_sql(topic)
            sql = f"""
                SELECT id, category, question, answer, difficulty, related_skills, embedding
                FROM interview_qa_pairs
                WHERE embedding IS NOT NULL AND embedding != ''
                {filter_sql}
            """
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def domain_fulltext_search(query: str, topic: Optional[str], limit: int = 5) -> List[Dict]:
    """域内全文检索"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            filter_sql, params = _domain_filter_sql(topic)
            sql = f"""
                SELECT id, category, question, answer, difficulty, related_skills,
                       MATCH(question) AGAINST(%s IN NATURAL LANGUAGE MODE) as score
                FROM interview_qa_pairs
                WHERE MATCH(question) AGAINST(%s IN NATURAL LANGUAGE MODE)
                {filter_sql}
                ORDER BY score DESC
                LIMIT %s
            """
            full_params = [query, query] + params + [limit]
            cur.execute(sql, full_params)
            rows = cur.fetchall()
            if rows and rows[0]["score"] > 0.5:
                return [dict(r) for r in rows]
    finally:
        conn.close()

    # 回退：关键词LIKE检索
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    eng = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", query)
    keywords = [w for w in cjk if len(w) >= 2] + eng
    if not keywords:
        return []

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # 精确匹配回退：在所有关键词中找到匹配最多的那条题
            candidates = set()
            for w in keywords:
                cur.execute(
                    "SELECT id, category, question, answer, difficulty, related_skills "
                    "FROM interview_qa_pairs WHERE question LIKE %s",
                    (f"%{w}%",),
                )
                for row in cur.fetchall():
                    candidates.add((row["id"], row["question"]))

            if candidates:
                import collections

                # 统计每道题被多少关键词匹配到
                counter = collections.Counter(qid for qid, _ in candidates)
                best_id = counter.most_common(1)[0][0]
                cur.execute(
                    "SELECT id, category, question, answer, difficulty, related_skills "
                    "FROM interview_qa_pairs WHERE id = %s",
                    (best_id,),
                )
                row = cur.fetchone()
                if row:
                    return [dict(row)]

            # 大范围LIKE检索
            conditions, params = [], []
            for w in keywords[:8]:
                conditions.append("(question LIKE %s OR answer LIKE %s)")
                params.extend([f"%{w}%", f"%{w}%"])
            filter_sql, filter_params = _domain_filter_sql(topic)
            sql = f"""
                SELECT id, category, question, answer, difficulty, related_skills
                FROM interview_qa_pairs
                WHERE ({" OR ".join(conditions)})
                {filter_sql}
                ORDER BY id
                LIMIT {limit * 3}
            """
            cur.execute(sql, params + filter_params)
            rows = cur.fetchall()
            if rows:

                def match_score(row):
                    q = row["question"]
                    return sum(1 for w in keywords if w.lower() in q.lower())

                rows.sort(key=match_score, reverse=True)
                return [dict(r) for r in rows[:limit]]
    finally:
        conn.close()
    return []


def domain_semantic_search(query: str, topic: Optional[str], limit: int = 5, threshold: float = 0.55) -> List[Dict]:
    """域内语义检索（主检索方案）

    核心方案：embedding语义匹配，能处理同义词和不同表达。
    阈值0.55比之前的0.65宽松，提升召回率。
    """
    qas = _load_qa_in_domain(topic)
    if not qas:
        return []

    query_vec = get_embedding(query)
    results = []
    for qa in qas:
        try:
            stored_vec = json.loads(qa["embedding"])
            sim = cosine_similarity(query_vec, stored_vec)
            results.append({**qa, "similarity": round(sim, 4)})
        except:
            continue

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return [r for r in results if r["similarity"] >= threshold][:limit]


def domain_exact_match(query: str, topic: Optional[str]) -> Optional[Dict]:
    """域内精确匹配"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if topic:
                topic_to_category = {
                    "RAG": "RAG",
                    "Agent": "Agent",
                    "大模型": "大模型",
                    "工程化": "工程化",
                    "Python": "Python",
                    "Prompt Engineering": "大模型",
                }
                cat = topic_to_category.get(topic)
                if cat:
                    cur.execute(
                        "SELECT id, category, question, answer, difficulty, related_skills "
                        "FROM interview_qa_pairs WHERE question = %s AND category = %s LIMIT 1",
                        (query, cat),
                    )
                    row = cur.fetchone()
                    if row:
                        return dict(row)
            # 无域限制的LIKE回退
            cur.execute(
                "SELECT id, category, question, answer, difficulty, related_skills "
                "FROM interview_qa_pairs WHERE question LIKE %s LIMIT 1",
                (f"%{query}%",),
            )
            row = cur.fetchone()
            if row:
                return dict(row)
    finally:
        conn.close()
    return None


# ===== 同域推荐 =====


def get_related_questions(
    question: str, topic: Optional[str], current_id: Optional[int] = None, limit: int = 3
) -> List[Dict]:
    """推荐同域内相关问题（排除当前匹配的题）"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            filter_sql, params = _domain_filter_sql(topic)
            sql = f"""
                SELECT id, question FROM interview_qa_pairs
                WHERE 1=1 {filter_sql}
                ORDER BY id
                LIMIT {limit * 3}
            """
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    # 排除当前问题，按关键词重叠排序
    q_words = set(re.findall(r"[\u4e00-\u9fff]{2,}", question.lower()))
    q_words.update(w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", question))

    scored = []
    for r in rows:
        if current_id and r["id"] == current_id:
            continue
        r_words = set(re.findall(r"[\u4e00-\u9fff]{2,}", r["question"].lower()))
        r_words.update(w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", r["question"]))
        overlap = len(q_words & r_words)
        scored.append((overlap, r["question"], r["id"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"question": q[1], "id": q[2]} for q in scored[:limit] if q[0] > 0]


# ===== 预置快捷回答 =====

SHORT_ANSWERS = {
    "什么是RAG": "RAG（Retrieval-Augmented Generation）即检索增强生成，将信息检索与大语言模型结合。核心：用户问题→检索文档→作为上下文→LLM生成。优势：无需训练、知识可更新、减少幻觉。",
    "什么是Agent": "AI Agent是能自主感知环境、制定计划并执行行动的智能体。核心特征：工具使用、记忆、规划、循环推理（ReAct）。区别于普通LLM调用，Agent能自主决策和执行多步任务。",
    "什么是Transformer": "Transformer是2017年Google提出的架构，核心是Self-Attention机制。由Encoder-Decoder组成，含多头注意力、FFN、残差连接和LayerNorm。BERT/GPT等大模型都基于此。",
    "什么是LoRA": "LoRA（Low-Rank Adaptation）通过在权重旁加低秩矩阵微调，只需训练0.1%-1%参数，大幅降低显存。QLoRA结合量化，单卡可微调大模型。",
    "什么是Prompt": "Prompt Engineering是通过设计输入提示引导LLM输出预期结果。核心技巧：角色设定、思维链(CoT)、Few-shot示例、结构化输出、负向提示、分步指令。",
    "什么是向量数据库": "向量数据库存储和检索高维向量，支持ANN搜索。主流：Milvus、FAISS、Pinecone、Qdrant、Weaviate。在RAG中用于存储文档embedding并做相似度检索。",
    "什么是微调": "微调是在预训练模型上用特定领域数据继续训练。常见方式：全参数微调、LoRA、Adapter。能显著提升特定任务表现。",
    "什么是embedding": "Embedding将文本映射到高维向量空间，语义相近的内容在空间中距离也近。常用模型：OpenAI text-embedding-3、nomic-embed-text、BGE。",
}


def check_short_answer(query: str) -> Optional[str]:
    """预置快捷回答"""
    if query in SHORT_ANSWERS:
        return SHORT_ANSWERS[query]
    for key, answer in SHORT_ANSWERS.items():
        if key in query or query in key:
            return answer
    return None


def ask_deepseek(question: str) -> str:
    """AI API兜底（从SQLite设置读取配置）"""
    import urllib.request, os, sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from backend.state import get_setting, init_db

    init_db()
    api_key = get_setting("ai_api_key") or ""
    api_url = (get_setting("ai_base_url") or "https://api.deepseek.com") + "/chat/completions"
    model = get_setting("ai_model") or "deepseek-chat"

    prompt = f"""你是一个AI应用开发专家。用户问了一个技术问题，请用简短（50-100字）、准确的方式回答。

用户问题：{question}

要求：
- 答案控制在50-100字
- 直接回答问题，不要铺垫
- 技术术语要准确
- 如果是概念性问题，给出定义+一句话解释"""

    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.2,
        }
    ).encode()
    req = urllib.request.Request(
        api_url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def _keyword_overlap(question: str, matched: str) -> float:
    """计算用户问题与匹配结果的关键词重叠比例"""
    q_words = set(re.findall(r"[\u4e00-\u9fff]{2,}", question.lower()))
    q_words.update(w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", question))
    m_words = set(re.findall(r"[\u4e00-\u9fff]{2,}", matched.lower()))
    m_words.update(w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", matched))
    if not q_words or not m_words:
        return 1.0
    overlap = len(q_words & m_words)
    return overlap / len(q_words) if q_words else 1.0


# ===== 主入口 =====


def fast_answer(question: str) -> Dict[str, Any]:
    """
    完整检索流程：
    L0: 缓存命中
    L0.5: 话题分类
    L1: 域内精确匹配 + LIKE
    L2: 域内语义检索（embedding匹配）
    L3: 预置短回答
    L4: DeepSeek兜底
    """
    start = time.time()

    # L0: 缓存
    cached = query_cache.get(question)
    if cached:
        elapsed = time.time() - start
        resp = {**cached, "layer": 0, "elapsed_ms": round(elapsed * 1000)}
        return resp

    # L0.5: 话题分类
    topic = classify_topic(question)

    # L1: 域内精确匹配 + LIKE
    result = domain_exact_match(question, topic)
    if result:
        elapsed = time.time() - start
        related = get_related_questions(result["question"], topic or result["category"], result["id"])
        resp = {
            "answer": result["answer"],
            "category": result["category"],
            "question": result["question"],
            "matched": result["question"],
            "topic": topic,
            "layer": 1,
            "elapsed_ms": round(elapsed * 1000),
            "related": related,
        }
        query_cache.set(question, resp)
        return resp

    # L2: 域内语义检索（主方案，embedding匹配）
    sem = domain_semantic_search(question, topic, threshold=SEMANTIC_MATCH_THRESHOLD)
    if sem:
        best = sem[0]
        elapsed = time.time() - start

        # 置信度检查：关键词重叠太低说明embedding只靠语义框架匹配而非真正理解
        overlap_ratio = _keyword_overlap(question, best["question"])

        # 低置信度（关键词完全没重叠）→ 放弃检索结果，走DeepSeek
        if overlap_ratio < 0.18:
            confidence = "low"
            # 不走缓存，直接降级到DeepSeek
            try:
                answer = ask_deepseek(question)
                ds_elapsed = time.time() - start
                resp = {
                    "answer": answer,
                    "category": "AI生成",
                    "question": question,
                    "matched": question,
                    "confidence": "low",
                    "topic": topic,
                    "layer": 4,
                    "elapsed_ms": round(ds_elapsed * 1000),
                    "related": [],
                    "note": "知识库中未找到精确匹配，以下为AI生成回答，仅供参考",
                }
                query_cache.set(question, resp)
                return resp
            except:
                # DeepSeek失败，退回检索结果
                pass

        confidence = "medium"
        related = get_related_questions(best["question"], topic or best["category"], best["id"])
        resp = {
            "answer": best["answer"],
            "category": best["category"],
            "question": best["question"],
            "matched": best["question"],
            "similarity": best.get("similarity", 0),
            "confidence": confidence,
            "topic": topic,
            "layer": 2,
            "elapsed_ms": round(elapsed * 1000),
            "related": related,
        }
        query_cache.set(question, resp)
        return resp

    # L3: 预置短回答
    preset = check_short_answer(question)
    if preset:
        elapsed = time.time() - start
        resp = {
            "answer": preset,
            "category": topic or "快速应答",
            "question": question,
            "matched": question,
            "topic": topic,
            "layer": 3,
            "elapsed_ms": round(elapsed * 1000),
            "related": [],
        }
        query_cache.set(question, resp)
        return resp

    # L4: DeepSeek兜底
    try:
        answer = ask_deepseek(question)
        elapsed = time.time() - start
        resp = {
            "answer": answer,
            "category": "AI生成",
            "question": question,
            "matched": question,
            "topic": topic,
            "layer": 4,
            "elapsed_ms": round(elapsed * 1000),
            "related": [],
        }
        query_cache.set(question, resp)
        return resp
    except Exception as e:
        elapsed = time.time() - start
        return {
            "answer": f"抱歉，未能找到答案。错误：{str(e)}。请换个问法试试。",
            "category": "未知",
            "question": question,
            "matched": question,
            "topic": topic,
            "layer": -1,
            "elapsed_ms": round(elapsed * 1000),
            "related": [],
        }
