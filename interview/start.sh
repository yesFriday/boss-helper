#!/bin/bash
# 面试问答Agent - 启动脚本
cd "$(dirname "$0")"
echo "🚀 启动面试问答Agent..."
echo "  LLM: qwen2.5:14b (ollama) ← 出题"
echo "  LLM: deepseek-chat (DeepSeek) ← 批改"
echo "  Embedding: nomic-embed-text (ollama)"
echo "  Database: MySQL ai_jobs_db"
echo "  Port: 8001"
echo ""
python3 -c "
import uvicorn
uvicorn.run('main:app', host='0.0.0.0', port=8001)
"
