import { api } from './client'
import type { SystemStatus, FunnelStats } from './types'

export const systemApi = {
  getStatus: () => api.get<SystemStatus>('/api/status'),
  getStats: () => api.get<FunnelStats>('/api/stats'),
  startSystem: () => api.post<{ status: string; message?: string }>('/api/system/start'),
  stopSystem: () => api.post('/api/system/stop'),
  relogin: () => api.post<{ status: string; message?: string }>('/api/system/relogin'),
  heartbeat: () => api.post<{ alive: boolean }>('/api/system/heartbeat'),
  pauseMonitor: () => api.post('/api/monitor/pause'),
  resumeMonitor: () => api.post('/api/monitor/resume'),
  navigateToChat: () => api.post('/api/system/navigate-chat'),
}
