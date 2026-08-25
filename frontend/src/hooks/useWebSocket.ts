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
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCountRef = useRef(0)
  const mountedRef = useRef(true)

  const handleMessage = useCallback(async (msg: WSMessage) => {
    const { addToast } = useNotificationStore.getState()

    switch (msg.type) {
      case 'connected':
        retryCountRef.current = 0
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
    if (!mountedRef.current) return

    const isDefaultPort = typeof window !== 'undefined' && location.port === '8010'
    const wsUrl = isDefaultPort
      ? `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`
      : 'ws://127.0.0.1:8010/ws'
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      retryCountRef.current = 0
    }

    ws.onmessage = (e) => {
      try {
        const msg: WSMessage = JSON.parse(e.data)
        handleMessage(msg)
      } catch {}
    }

    ws.onclose = () => {
      wsRef.current = null
      if (!mountedRef.current) return

      const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000)
      retryCountRef.current += 1
      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      wsRef.current?.close()
    }
  }, [handleMessage])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])
}
