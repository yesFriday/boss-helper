import { useState, useEffect, useRef } from 'react'
import { MessageSquare, ExternalLink } from 'lucide-react'
import { EmptyState } from '../components/common/EmptyState'
import { Spinner } from '../components/common/Spinner'
import { useChatStore } from '../stores/chatStore'
import { useNotificationStore } from '../stores/notificationStore'
import { conversationsApi } from '../api/conversations'
import { systemApi } from '../api/system'
import { cn } from '../lib/cn'

export function ChatPage() {
  const { conversations, activeConvId, messages } = useChatStore()
  const { addToast } = useNotificationStore()
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [msgLoading, setMsgLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadConversations()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadConversations = async () => {
    setLoading(true)
    try {
      const res = await conversationsApi.listConversations()
      useChatStore.getState().setConversations(res.conversations || [])
    } catch {} finally { setLoading(false) }
  }

  const selectConversation = async (id: number) => {
    useChatStore.getState().setActiveConvId(id)
    setMsgLoading(true)
    try {
      const res = await conversationsApi.getMessages(id)
      useChatStore.getState().setMessages(res.messages || [])
    } catch {} finally { setMsgLoading(false) }
  }

  const handleSend = async () => {
    if (!activeConvId || !input.trim()) return
    const content = input.trim()
    try {
      await conversationsApi.sendMessage(activeConvId, content)
      setInput('')
      const res = await conversationsApi.getMessages(activeConvId)
      useChatStore.getState().setMessages(res.messages || [])
      loadConversations()
    } catch {
      addToast('发送失败', 'error')
    }
  }

  const handleToggleAutoReply = async () => {
    if (!activeConvId) return
    const conv = conversations.find((c) => c.id === activeConvId)
    if (!conv) return
    try {
      await conversationsApi.toggleAutoReply(activeConvId, !conv.auto_reply_enabled)
      loadConversations()
    } catch {}
  }

  const handleOpenInBrowser = async () => {
    await systemApi.navigateToChat()
  }

  const activeConv = conversations.find((c) => c.id === activeConvId)

  return (
    <div className="animate-slide-in">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-slate-400">数据库会话记录</span>
        <button
          onClick={handleOpenInBrowser}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
        >
          <ExternalLink size={12} />
          在浏览器中打开BOSS聊天页
        </button>
      </div>

      <div className="flex h-[70vh] bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="w-70 border-r border-slate-200 overflow-y-auto bg-slate-50">
          {loading ? (
            <div className="flex items-center justify-center py-8"><Spinner size="sm" /></div>
          ) : conversations.length > 0 ? (
            conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => selectConversation(conv.id)}
                className={cn(
                  'p-3.5 cursor-pointer border-b border-slate-200 transition-all',
                  activeConvId === conv.id ? 'bg-white border-l-3 border-l-indigo-500' : 'hover:bg-white'
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-sm text-slate-800">{conv.hr_name || '未知'}</div>
                  {conv.unread_count > 0 && (
                    <span className="px-2 py-0.5 bg-indigo-500 text-white rounded-full text-xs font-bold">
                      {conv.unread_count}
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400 mt-1 truncate">
                  {conv.last_message_text?.slice(0, 40)}
                </div>
                <div className="text-xs text-slate-300 mt-1">
                  {conv.hr_company} · {conv.job_title?.slice(0, 15)}
                </div>
              </div>
            ))
          ) : (
            <div className="p-5 text-center text-slate-400 text-sm">暂无会话</div>
          )}
        </div>

        <div className="flex-1 flex flex-col">
          <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between bg-white">
            <div>
              <div className="font-bold text-base text-slate-800">{activeConv?.hr_name || '选择会话'}</div>
              {activeConv && (
                <div className="text-xs text-slate-400 mt-0.5">
                  {activeConv.hr_company} · {activeConv.job_title?.slice(0, 20)}
                </div>
              )}
            </div>
            {activeConv && (
              <div className="flex gap-2">
                <button
                  onClick={handleToggleAutoReply}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
                >
                  {activeConv.auto_reply_enabled ? '暂停AI回复' : '开启AI回复'}
                </button>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3 bg-slate-50">
            {msgLoading ? (
              <div className="flex items-center justify-center h-full"><Spinner size="md" /></div>
            ) : messages.length > 0 ? (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    'max-w-[80%] p-3 rounded-xl shadow-sm',
                    msg.sender === 'hr'
                      ? 'self-start bg-white border border-slate-200'
                      : msg.ai_generated
                        ? 'self-end bg-gradient-to-r from-emerald-500 to-teal-500 text-white'
                        : 'self-end bg-gradient-to-r from-indigo-500 to-purple-500 text-white'
                  )}
                >
                  <div className={cn('text-xs font-semibold mb-1.5', msg.sender === 'hr' ? 'text-slate-400 uppercase tracking-wider' : 'text-white/80')}>
                    {msg.sender === 'hr' ? 'HR' : msg.ai_generated ? '我 (AI代发)' : '我'}
                  </div>
                  <div className="text-sm leading-relaxed">{msg.content}</div>
                </div>
              ))
            ) : (
              <EmptyState
                icon={<MessageSquare size={48} />}
                title="选择一个会话查看消息"
                description="点击左侧会话开始查看"
              />
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="p-4 border-t border-slate-200 bg-white">
            <div className="flex gap-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder="输入消息..."
                rows={1}
                className="flex-1 px-4 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all resize-none"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="px-5 py-2.5 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-500 shadow-sm hover:shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex-shrink-0"
              >
                发送
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}