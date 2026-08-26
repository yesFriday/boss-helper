import { useState, useEffect, useRef } from 'react'
import { MessageSquare, ExternalLink, AlertTriangle } from 'lucide-react'
import { Button } from '../components/common/Button'
import { EmptyState } from '../components/common/EmptyState'
import { Spinner } from '../components/common/Spinner'
import { useChatStore } from '../stores/chatStore'
import { useNotificationStore } from '../stores/notificationStore'
import { conversationsApi } from '../api/conversations'
import { systemApi } from '../api/system'
import { cn } from '../lib/cn'

export function ChatPage() {
  const { conversations, activeConvId, messages, dangerFilter } = useChatStore()
  const setDangerFilter = useChatStore((s) => s.setDangerFilter)
  const { addToast } = useNotificationStore()
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [msgLoading, setMsgLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadConversations()
  }, [])

  useEffect(() => {
    loadConversations()
  }, [dangerFilter])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadConversations = async () => {
    setLoading(true)
    try {
      const filter = dangerFilter ? 'dangerous' : undefined
      const res = await conversationsApi.listConversations(filter)
      useChatStore.getState().setConversations(res.conversations || [])
    } catch { } finally { setLoading(false) }
  }

  const selectConversation = async (id: number) => {
    useChatStore.getState().setActiveConvId(id)
    setMsgLoading(true)
    try {
      const res = await conversationsApi.getMessages(id)
      useChatStore.getState().setMessages(res.messages || [])
    } catch { } finally { setMsgLoading(false) }
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
    } catch { }
  }

  const handleOpenInBrowser = async () => {
    await systemApi.navigateToChat()
  }

  const activeConv = conversations.find((c) => c.id === activeConvId)

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <span className="text-xs text-slate-400">数据库会话记录</span>
        <button
          onClick={handleOpenInBrowser}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 transition-colors cursor-pointer"
        >
          <ExternalLink size={12} />
          在浏览器中打开
        </button>
      </div>

      {/* Chat panel - fills remaining height */}
      <div className="flex-1 min-h-0 flex bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="w-64 flex-shrink-0 overflow-y-auto bg-white border-r border-slate-100">
          {/* Filter tabs */}
          <div className="flex border-b border-slate-100 flex-shrink-0">
            <button
              onClick={() => setDangerFilter(false)}
              className={cn(
                'flex-1 py-2.5 text-xs font-medium transition-colors cursor-pointer',
                !dangerFilter ? 'text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:text-slate-700'
              )}
            >
              全部
            </button>
            <button
              onClick={() => setDangerFilter(true)}
              className={cn(
                'flex-1 py-2.5 text-xs font-medium transition-colors cursor-pointer flex items-center justify-center gap-1',
                dangerFilter ? 'text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:text-slate-700'
              )}
            >
              <AlertTriangle size={12} />
              风险
            </button>
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-8"><Spinner size="sm" /></div>
          ) : conversations.length > 0 ? (
            conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => selectConversation(conv.id)}
                className={cn(
                  'px-3 py-2.5 cursor-pointer transition-colors border-b border-slate-50',
                  activeConvId === conv.id ? 'bg-blue-50' : 'hover:bg-slate-50'
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <div className={cn(
                      'text-sm font-medium truncate',
                      activeConvId === conv.id ? 'text-blue-700' : 'text-slate-900'
                    )}>
                      {conv.hr_name || '未知'}
                    </div>
                    {conv.unread_count > 0 && (
                      <span className="bg-red-500 h-2 w-2 rounded-full flex-shrink-0" />
                    )}
                    {conv.is_dangerous ? (
                      <span className="px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded text-[10px] font-medium flex items-center gap-0.5 flex-shrink-0">
                        <AlertTriangle size={10} />
                        风险
                      </span>
                    ) : null}
                  </div>
                  <div className="text-[11px] text-slate-400 truncate flex-shrink-0">
                    {conv.hr_company}
                  </div>
                </div>
                <div className="text-xs text-slate-500 mt-1 truncate">
                  {conv.last_message_text?.slice(0, 30)}
                </div>
                <div className="text-[11px] text-slate-400 mt-0.5 truncate">
                  {conv.job_title?.slice(0, 12)}
                </div>
              </div>
            ))
          ) : (
            <div className="p-5 text-center text-slate-400 text-sm">暂无会话</div>
          )}
        </div>

        <div className="flex-1 min-w-0 flex flex-col">
          <div className="px-4 py-2.5 border-b border-slate-100 flex items-center justify-between bg-white flex-shrink-0">
            <div className="min-w-0">
              <div className="text-sm font-medium text-slate-900 truncate">{activeConv?.hr_name || '选择会话'}</div>
              {activeConv && (
                <div className="text-xs text-slate-400 mt-0.5 truncate">
                  {activeConv.hr_company} · {activeConv.job_title?.slice(0, 20)}
                </div>
              )}
            </div>
            {activeConv && (
              <button
                onClick={handleToggleAutoReply}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer border flex-shrink-0 ml-2',
                  activeConv.auto_reply_enabled
                    ? 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                )}
              >
                {activeConv.auto_reply_enabled ? '暂停AI回复' : '开启AI回复'}
              </button>
            )}
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-3 bg-slate-50/50">
            {msgLoading ? (
              <div className="flex items-center justify-center h-full"><Spinner size="md" /></div>
            ) : messages.length > 0 ? (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn('max-w-[75%] flex flex-col', msg.sender === 'hr' ? 'self-start' : 'self-end items-end')}
                >
                  <div
                    className={cn(
                      'px-3.5 py-2.5 rounded-lg text-sm leading-relaxed shadow-sm',
                      msg.sender === 'hr'
                        ? 'bg-white text-slate-800 border border-slate-100 rounded-tl-sm'
                        : msg.ai_generated
                          ? 'bg-blue-500/90 text-white rounded-tr-sm'
                          : 'bg-blue-600 text-white rounded-tr-sm'
                    )}
                  >
                    {msg.content}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-[11px] text-slate-400">
                    {msg.ai_generated ? (
                      <span className="px-1.5 py-px rounded bg-blue-50 text-blue-600 text-[10px] font-medium">AI</span>
                    ) : null}
                    <span>{msg.sender === 'hr' ? 'HR' : '我'}</span>
                    <span>{new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState
                icon={<MessageSquare size={48} className="text-slate-300" />}
                title="选择一个会话查看消息"
                description="点击左侧列表中的 HR 开始对话"
              />
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="p-3 border-t border-slate-100 bg-white flex-shrink-0">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder="输入消息,Enter 发送,Shift+Enter 换行..."
                rows={1}
                className="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 transition-colors resize-none"
              />
              <Button
                variant="primary"
                size="sm"
                onClick={handleSend}
                disabled={!input.trim()}
                className="flex-shrink-0 px-4"
              >
                发送
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
