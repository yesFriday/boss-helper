"""
面试问答Agent - LLM客户端模块 (LangChain 重构)
- Embedding: Ollama nomic-embed-text
- 出题: Ollama qwen2.5:14b (通过 LangChain ChatOllama)
- 聊天/批改: 通过 LangChain ChatOpenAI 接入任意 OpenAI 兼容 API
"""

import json
import re
from typing import List, Optional, Dict, Any

import httpx
import numpy as np
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

# ── Ollama 本地配置 ──
OLLAMA_BASE = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "qwen2.5:14b"


# ── AI 配置（每次调用时从 SQLite 设置实时读取） ──
def _load_ai_config() -> Dict[str, str]:
    """从 SQLite settings 表读取 AI 配置。每次调用都实时读取，前端修改即时生效。"""
    cfg = {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    }
    try:
        import sys, os

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.state import get_setting, get_db

        get_db()
        key = get_setting("ai_api_key")
        if key:
            cfg["api_key"] = key
        url = get_setting("ai_base_url")
        is_full = get_setting("ai_is_full_url", "false") == "true"
        if url:
            u = url.strip().rstrip("/")
            if is_full:
                if u.endswith("/chat/completions"):
                    u = u[:-len("/chat/completions")].rstrip("/")
            else:
                if u.endswith("/chat/completions"):
                    u = u[:-len("/chat/completions")].rstrip("/")
            cfg["base_url"] = u
        model = get_setting("ai_model")
        if model:
            cfg["model"] = model
    except Exception:
        pass
    return cfg


# ── LangChain 工厂函数 ──
def get_llm(temperature: float = 0.3) -> ChatOpenAI:
    """
    创建 LangChain ChatOpenAI 实例。
    每次调用从 SQLite 实时读取 api_key / base_url / model，
    前端修改设置后下一次对话即时生效，无需重启服务。
    """
    cfg = _load_ai_config()
    if not cfg["api_key"]:
        raise RuntimeError("AI API Key未配置，请在设置页配置")
    return ChatOpenAI(
        model=cfg["model"],
        openai_api_key=cfg["api_key"],
        openai_api_base=cfg["base_url"],
        temperature=temperature,
        max_retries=3,
        timeout=120,
    )


def get_llm_with_tools(tools: list, temperature: float = 0.7) -> ChatOpenAI:
    """
    创建绑定了工具调用的 ChatOpenAI 实例（Agent 用）。
    绑定后 LLM 可以自主决定调用 tools 中定义的工具。
    tools 格式为 OpenAI function-calling 的 dict 列表。
    """
    llm = get_llm(temperature)
    return llm.bind_tools(tools)


def get_ollama_llm(temperature: float = 0.7) -> ChatOllama:
    """创建 LangChain ChatOllama 实例（面试出题用）。"""
    return ChatOllama(
        model=LLM_MODEL,
        temperature=temperature,
        base_url=OLLAMA_BASE,
    )


# ── Embedding ──
def get_embedding(text: str) -> List[float]:
    """获取文本的 embedding 向量（Ollama nomic-embed-text）"""
    resp = httpx.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embeddings"][0]


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """计算余弦相似度"""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ── 兼容旧接口（内部使用 LangChain，外部调用方无需修改） ──
def _dict_messages_to_lc(messages: list, system_prompt: Optional[str] = None) -> List[BaseMessage]:
    """将 dict 格式的消息列表转为 LangChain BaseMessage 列表"""
    lc_messages: List[BaseMessage] = []
    if system_prompt:
        lc_messages.append(SystemMessage(content=system_prompt))
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages


def llm_chat_ollama(
    messages: list, system_prompt: Optional[str] = None, temperature: float = 0.7
) -> str:
    """
    调用 Ollama 大模型（面试出题用）。
    兼容旧接口，内部使用 LangChain ChatOllama。
    """
    llm = get_ollama_llm(temperature)
    lc_messages = _dict_messages_to_lc(messages, system_prompt)
    response = llm.invoke(lc_messages)
    return response.content


def parse_json_from_llm(text: str) -> Optional[dict]:
    """从 LLM 返回文本中提取 JSON"""
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return None