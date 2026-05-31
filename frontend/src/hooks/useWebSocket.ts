import { useEffect, useRef, useCallback } from 'react'
import type { WSMessage } from '../api/types'
import { useSystemStore } from '../stores/systemStore'
import { useJobsStore } from '../stores/jobsStore'
import { useChatStore } from '../stores/chatStore'
import { useNotificationStore } from '../stores/notificationStore'
import { useSchedulerStore } from '../stores/schedulerStore'
import { systemApi } from '../api/system'
import { jobsApi } from '../api/jobs'
import { conversationsApi } from '../api/conversations'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)

  const handleMessage = useCallback(async (msg: WSMessage) => {
    const { addToast } = useNotificationStore.getState()

    switch (msg.type) {
      case 'connected':
        useSystemStore.getState().updateFromStatus(msg.status as any)
        break
      case 'search_complete':
        useJobsStore.getState().setSearchStatusMessage(`搜索完成，找到 ${msg.found} 条`)
        useJobsStore.getState().setSearchInFlight(false)
        const jobsRes = await jobsApi.listJobs({ limit: 50 })
        useJobsStore.getState().setSearchJobs(jobsRes.jobs || [])
        break
      case 'apply_complete':
        if (msg.job_url) {
          useJobsStore.getState().updateJobStatus(msg.job_url as string, 'applied')
        }
        const stats = await systemApi.getStats()
        useJobsStore.getState().setFunnel({
          pending: stats.pending || 0,
          today: stats.today_applications || 0,
          replied: stats.replied || 0,
          interview: stats.interview || 0,
        })
        break
      case 'batch_complete': {
        const res = await jobsApi.listJobs({ limit: 50 })
        useJobsStore.getState().setSearchJobs(res.jobs || [])
        const stats2 = await systemApi.getStats()
        useJobsStore.getState().setFunnel({
          pending: stats2.pending || 0,
          today: stats2.today_applications || 0,
          replied: stats2.replied || 0,
          interview: stats2.interview || 0,
        })
        break
      }
      case 'new_messages':
      case 'auto_reply_sent':
      case 'manual_message_sent': {
        const convs = await conversationsApi.listConversations()
        useChatStore.getState().setConversations(convs.conversations || [])
        const { activeConvId } = useChatStore.getState()
        if (activeConvId) {
          const msgs = await conversationsApi.getMessages(activeConvId)
          useChatStore.getState().setMessages(msgs.messages || [])
        }
        break
      }
      case 'session_expired':
        useSystemStore.getState().setSessionStatus('expired')
        addToast('登录已过期', 'error')
        break
      case 'relogin_ok':
        useSystemStore.getState().setSessionStatus('ok')
        addToast('登录成功', 'success')
        break
      case 'monitor_paused':
      case 'monitor_resumed':
      case 'system': {
        const status = await systemApi.getStatus()
        useSystemStore.getState().updateFromStatus(status)
        break
      }
      case 'scheduler_tick': {
        if (msg.log) {
          useSchedulerStore.getState().addExecutionLog(msg.log as { time: string; tasks: string[] })
        }
        break
      }
      case 'scheduler_config_updated': {
        if (msg.config) {
          useSchedulerStore.getState().setConfig(msg.config as any)
        }
        break
      }
    }
  }, [])

  const connect = useCallback(() => {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${location.host}/ws`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const msg: WSMessage = JSON.parse(e.data)
        handleMessage(msg)
      } catch {}
    }

    ws.onclose = () => {
      reconnectTimerRef.current = window.setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()
  }, [handleMessage])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}
