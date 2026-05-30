"""
面试问答Agent - 面试引擎核心
出题（qwen2.5:14b）+ 批改（DeepSeek）+ 自动存入问答对
"""

import uuid
import json
import re
from typing import Optional, List, Dict, Any
from llm_client import llm_chat_ollama, llm_chat_deepseek, parse_json_from_llm
from db import (semantic_search_qa, search_jobs_by_semantic,
                save_interview_record, add_qa_pair, get_all_job_categories)


class InterviewEngine:
    """面试引擎"""

    # 面试题分类和权重
    CATEGORIES = {
        "RAG": {"weight": 0.30, "keywords": ["rag", "检索增强", "检索", "召回", "rerank", "chunk",
                                               "embedding", "向量数据库", "doc store", "文档检索"]},
        "Agent": {"weight": 0.25, "keywords": ["agent", "智能体", "tool use", "function calling",
                                                 "multi-agent", "planning", "reAct", "memory"]},
        "大模型": {"weight": 0.20, "keywords": ["llm", "大模型", "微调", "fine-tuning", "prompt",
                                                 "prompt engineering", "transformer", "attention"]},
        "工程化": {"weight": 0.15, "keywords": ["fastapi", "docker", "部署", "api", "性能优化",
                                                 "缓存", "并发", "异步"]},
        "Python": {"weight": 0.10, "keywords": ["python", "异步", "装饰器", "生成器", "类型提示",
                                                  "pydantic", "asyncio"]},
    }

    def __init__(self, job_focus: str = ""):
        self.session_id = uuid.uuid4().hex[:12]
        self.job_focus = job_focus
        self.asked_questions = set()  # 防止重复出题
        self.asked_count = 0
        self.current_question_data = None  # 当前题目完整数据（用于批改后存库）
        self.current_question_id = None
        self.job_context = ""
        self._init_context()

    def _init_context(self):
        """初始化面试上下文"""
        if self.job_focus:
            matched_jobs = search_jobs_by_semantic(self.job_focus, limit=3)
            if matched_jobs:
                self.job_context = "\n".join([
                    f"- {j['title']} @ {j['company']} ({j['salary']}) "
                    f"[匹配度: {j.get('similarity', 0):.0%}]"
                    for j in matched_jobs
                ])

    def _get_category_weights(self) -> Dict[str, float]:
        """根据岗位方向调整分类权重"""
        if not self.job_focus:
            return {k: v["weight"] for k, v in self.CATEGORIES.items()}

        focus_lower = self.job_focus.lower()
        weights = {}
        for cat, info in self.CATEGORIES.items():
            w = info["weight"]
            bonus = sum(0.05 for kw in info["keywords"] if kw in focus_lower)
            weights[cat] = w + bonus
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}

    def next_question(self) -> Dict[str, Any]:
        """生成下一道面试题（用qwen2.5:14b）"""
        self.asked_count += 1
        weights = self._get_category_weights()

        # 选分类（按权重随机）
        import random
        r = random.random()
        cumulative = 0
        chosen_category = list(self.CATEGORIES.keys())[0]
        for cat, w in weights.items():
            cumulative += w
            if r <= cumulative:
                chosen_category = cat
                break

        # 构建出题上下文
        focus_text = self.job_focus or "AI应用开发（RAG方向）"
        context_prompt = f"当前岗位方向：{focus_text}\n"
        if self.job_context:
            context_prompt += f"匹配到的相关岗位：\n{self.job_context}\n"
        context_prompt += f"当前面试领域：{chosen_category}（这是第{self.asked_count}题）"

        system_prompt = """你是一个专业的AI应用开发面试官，专注于RAG/Agent/大模型应用开发方向的面试出题。

你的任务是出一道高质量的技术面试题，并给出参考答案要点。

出题原则：
1. 问题要结合实际项目场景，不要纯理论
2. 涉及技术细节和最佳实践
3. 能考察候选人的工程能力
4. 难度适中（别太简单也别太偏）

输出格式（严格JSON，不要包含其他文字）：
{
  "category": "分类名",
  "question": "面试题内容",
  "difficulty": "easy/medium/hard",
  "skills": ["技能1", "技能2"],
  "reference_answer": "参考答案要点（300字以内）",
  "tips": ["答题技巧提示1", "答题技巧提示2"]
}"""

        # 尝试最多3次生成不同的题目
        for attempt in range(3):
            result = llm_chat_ollama(
                [{"role": "user", "content": context_prompt}],
                system_prompt=system_prompt,
                temperature=0.8 + attempt * 0.1,
            )

            q_data = parse_json_from_llm(result)
            if q_data and q_data.get("question"):
                dedup_key = q_data["question"][:30]
                if dedup_key not in self.asked_questions:
                    self.asked_questions.add(dedup_key)

                    self.current_question_data = {
                        "category": q_data.get("category", chosen_category),
                        "question": q_data["question"],
                        "reference_answer": q_data.get("reference_answer", ""),
                        "difficulty": q_data.get("difficulty", "medium"),
                        "skills": q_data.get("skills", []),
                    }
                    self.current_question_id = None

                    return {
                        "session_id": self.session_id,
                        "question_number": self.asked_count,
                        "category": self.current_question_data["category"],
                        "question": self.current_question_data["question"],
                        "difficulty": self.current_question_data["difficulty"],
                        "skills": self.current_question_data["skills"],
                        "reference_answer": self.current_question_data["reference_answer"],
                        "tips": q_data.get("tips", []),
                    }

        # 保底：从知识库取
        return self._fallback_question(chosen_category)

    def _fallback_question(self, category: str) -> Dict[str, Any]:
        """从知识库取出题"""
        results = semantic_search_qa(
            f"{self.job_focus or 'AI应用开发'} {category}",
            category=category, limit=5,
        )

        for r in results:
            dedup_key = r["question"][:30]
            if dedup_key not in self.asked_questions:
                self.asked_questions.add(dedup_key)

                self.current_question_data = {
                    "category": r["category"],
                    "question": r["question"],
                    "reference_answer": r["answer"],
                    "difficulty": r["difficulty"],
                    "skills": r.get("skills", "").split(",") if r.get("skills") else [],
                }
                self.current_question_id = r["id"]

                return {
                    "session_id": self.session_id,
                    "question_number": self.asked_count,
                    "category": r["category"],
                    "question": r["question"],
                    "difficulty": r["difficulty"],
                    "skills": self.current_question_data["skills"],
                    "reference_answer": r["answer"],
                    "tips": [],
                }

        # 兜底
        fallback_q = f"请说说你对{self.job_focus or 'AI应用开发'}方向的理解和项目经验"
        self.current_question_data = {
            "category": "通用",
            "question": fallback_q,
            "reference_answer": "（无预设答案）",
            "difficulty": "medium",
            "skills": [],
        }
        self.current_question_id = None
        return {
            "session_id": self.session_id,
            "question_number": self.asked_count,
            "category": "通用",
            "question": fallback_q,
            "difficulty": "medium",
            "skills": [],
            "reference_answer": "（无预设答案）",
            "tips": ["结合你的实际项目经验来回答", "突出技术难点和解决方案"],
        }

    def grade(self, question: str, user_answer: str,
              reference_answer: str = "") -> Dict[str, Any]:
        """批改回答（用DeepSeek）"""
        system_prompt = """你是一个专业的AI应用开发面试官。请对候选人的回答进行批改评分。

评分维度（每项1-10分）：
1. 技术准确性：概念是否准确、技术细节是否正确
2. 完整性：是否覆盖问题的关键维度
3. 实践经验：是否体现实际项目经验，有具体案例
4. 表达清晰度：逻辑是否清晰、有条理

总分 = (技术准确性×0.35 + 完整性×0.25 + 实践经验×0.25 + 表达清晰度×0.15)

输出格式（严格JSON，只输出JSON，不要其他文字）：
{
  "accuracy_score": 8,
  "completeness_score": 7,
  "practice_score": 6,
  "clarity_score": 8,
  "total_score": 7.3,
  "feedback": "详细批改意见（指出优点和不足）",
  "improvement": "具体改进建议",
  "follow_up": ["追问问题1", "追问问题2"]
}"""

        context = f"面试题：{question}\n"
        if reference_answer:
            context += f"参考答案要点：{reference_answer}\n"
        context += f"候选人的回答：{user_answer}"

        # 使用DeepSeek批改
        result = llm_chat_deepseek(
            [{"role": "user", "content": context}],
            system_prompt=system_prompt,
            temperature=0.3,
        )

        grade = parse_json_from_llm(result)
        if not grade:
            grade = {
                "accuracy_score": 5,
                "completeness_score": 5,
                "practice_score": 5,
                "clarity_score": 5,
                "total_score": 5.0,
                "feedback": result[:500],
                "improvement": "请参考上面批改详情",
                "follow_up": [],
            }

        total_score = grade.get("total_score", 5.0)
        feedback_text = grade.get("feedback", "")

        # 1. 保存面试记录
        save_interview_record(
            session_id=self.session_id,
            question_id=self.current_question_id,
            question=question,
            user_answer=user_answer,
            score=total_score,
            feedback=feedback_text,
            job_focus=self.job_focus,
        )

        # 2. 自动存入问答对（如果没有source_job_id说明是LLM新出的题）
        if self.current_question_id is None and self.current_question_data:
            try:
                cat = self.current_question_data.get("category", "通用")
                ref_answer = self.current_question_data.get("reference_answer", "")
                difficulty = self.current_question_data.get("difficulty", "medium")
                skills_list = self.current_question_data.get("skills", [])
                skills_str = ",".join(skills_list) if isinstance(skills_list, list) else ""

                add_qa_pair(
                    category=cat,
                    question=question,
                    answer=ref_answer,
                    difficulty=difficulty,
                    skills=skills_str,
                )
            except Exception as e:
                print(f"[WARN] 自动存入问答对失败: {e}")

        return grade

    def end_session(self) -> Dict[str, Any]:
        """结束面试，生成总结"""
        from db import get_session_summary
        summary = get_session_summary(self.session_id)

        if summary["total_questions"] == 0:
            return {"message": "本次没有面试记录"}

        low_scores = [r for r in summary["records"]
                     if r["score"] is not None and r["score"] < 6]

        prompt = f"""本次面试共{summary['total_questions']}题，平均得分{summary['avg_score']}分。
最高分：{summary['max_score']}，最低分：{summary['min_score']}。

低分题目（{len(low_scores)}题）：
{chr(10).join(f'- {r["question"][:50]}... (得分: {r["score"]})' for r in low_scores[:5])}

岗位方向：{self.job_focus or '通用'}

请给出面试总结和建议：
1. 整体表现评价
2. 薄弱环节（需要重点加强的方向）
3. 下一步学习建议
4. 推荐重点准备的面试话题"""

        review = llm_chat_ollama(
            [{"role": "user", "content": prompt}],
            temperature=0.5,
        )

        return {
            "session_id": self.session_id,
            "total_questions": summary["total_questions"],
            "avg_score": summary["avg_score"],
            "max_score": summary["max_score"],
            "min_score": summary["min_score"],
            "low_scores": low_scores[:5],
            "review": review,
        }
