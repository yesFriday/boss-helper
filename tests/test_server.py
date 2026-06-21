import sys
from pathlib import Path
from datetime import datetime
import json

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from backend.replier import SYSTEM_PROMPT, output_parser
from backend.interview.llm_client import get_llm

app = FastAPI(title="AI Agent Chat Test Sandbox")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TestReplyRequest(BaseModel):
    # Configuration
    current_time: Optional[str] = None
    pref_format: str = "both"
    pref_slots: str = "上午(9:00-12:00)，下午(14:00-18:00)"
    
    # Custom Database State
    occupied_interviews: List[Dict[str, str]] = [] # list of {"start_time": "", "end_time": "", "type": "online"/"offline", "company": "", "job": ""}
    
    # Job Info
    company: str = "未指定公司"
    job_title: str = "未指定岗位"
    job_desc: str = ""
    
    # User Profile
    resume_summary: str = ""
    wechat_id: str = ""
    
    # Dialogue
    history: List[Dict[str, str]] = [] # list of {"sender": "hr"/"me", "content": ""}
    new_hr_message: str

def format_mock_context(req: TestReplyRequest) -> str:
    parts = []
    
    # 1. System time
    st_str = req.current_time or datetime.now().strftime("%Y-%m-%d %H:%M")
    parts.append(f"【当前系统基准时间】: {st_str}")
    
    # 2. Preferences
    format_cn = {"online": "仅接受线上面试", "offline": "仅接受线下面试", "both": "线上线下均可"}.get(req.pref_format, "线上线下均可")
    parts.append(f"【我的面试形式偏好】: {format_cn}")
    parts.append(f"【我的期望面试时间段】: {req.pref_slots}")
    
    # 3. Occupied schedules
    parts.append("\n【求职者未来3天已有面试日程（请严格避开冲突）】:")
    if not req.occupied_interviews:
        parts.append("  (目前未来3天没有任何面试安排，全部时间均为空闲)")
    else:
        for item in req.occupied_interviews:
            t_type = "线上" if item.get("type") == "online" else "线下"
            parts.append(
                f"  - {item.get('start_time')} 至 {item.get('end_time')} ({t_type}) | 公司: {item.get('company')} | 岗位: {item.get('job')}"
            )
            
    # 4. Job Info
    parts.append("\n【岗位基本信息】")
    parts.append(f"招聘方公司: {req.company}")
    parts.append(f"应聘岗位: {req.job_title}")
    if req.job_desc:
        parts.append(f"岗位描述: {req.job_desc[:500]}")
        
    # 5. Profile
    if req.resume_summary:
        parts.append(f"我的简历摘要: {req.resume_summary}")
    if req.wechat_id:
        from backend.replier import _encode_wechat
        encoded = _encode_wechat(req.wechat_id)
        parts.append(f"求职者微信: {req.wechat_id}（BOSS会过滤微信号，实际发送时请用编码形式: {encoded}，不要发原始形式）")
    else:
        parts.append("求职者微信: 未设置")
        
    # 6. Dialogue history
    if req.history:
        parts.append("\n最近的对话记录:")
        for m in req.history:
            sender_label = "HR" if m.get("sender") == "hr" else "我"
            parts.append(f"  {sender_label}: {m.get('content')}")
            
    parts.append(f"\nHR刚刚说: {req.new_hr_message}")
    
    return "\n".join(parts)

@app.post("/api/test-reply")
def test_reply_endpoint(req: TestReplyRequest):
    try:
        context = format_mock_context(req)
        
        system_content = (
            SYSTEM_PROMPT.format(format_instructions=output_parser.get_format_instructions())
            + "\n\n本次回复风格: 语气正式专业"
        )
        
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=context),
        ]
        
        llm = get_llm(temperature=0.7)
        raw = llm.invoke(messages).content
        
        try:
            parsed = output_parser.parse(raw)
            return {
                "status": "ok",
                "raw_response": raw,
                "parsed": parsed.dict(),
                "rendered_prompt_context": context,
                "rendered_system_prompt": system_content
            }
        except Exception as pe:
            return {
                "status": "parse_error",
                "raw_response": raw,
                "error": f"JSON 解析失败: {str(pe)}",
                "rendered_prompt_context": context
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/")
def serve_index():
    index_html = Path(__file__).parent / "index.html"
    if index_html.exists():
        return HTMLResponse(content=index_html.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>index.html not found!</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    print("Starting AI Agent Test Server on http://localhost:8020")
    uvicorn.run(app, host="127.0.0.1", port=8020)
