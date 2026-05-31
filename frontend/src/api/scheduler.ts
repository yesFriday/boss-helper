import { api } from './client'

export interface SchedulerConfig {
  enabled: boolean
  days: number[]
  time_ranges: { start: string; end: string }[]
  auto_apply: {
    keyword: string
    city: string
    daily_limit: number
  }
  auto_reply: {
    style: string
  }
}

export interface SchedulerStatus {
  active: boolean
  phase: 'idle' | 'searching' | 'applying' | 'paused'
  today_count: number
  daily_limit: number
  execution_log: { time: string; tasks: string[] }[]
}

export const schedulerApi = {
  getConfig: () => api.get<{ config: SchedulerConfig }>('/api/scheduler'),
  updateConfig: (data: SchedulerConfig) => api.put('/api/scheduler', data),
  getStatus: () => api.get<SchedulerStatus>('/api/scheduler/status'),
}
