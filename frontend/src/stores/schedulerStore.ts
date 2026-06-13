import { create } from 'zustand'
import type { SchedulerConfig, SchedulerStatus } from '../api/scheduler'

const DEFAULT_CONFIG: SchedulerConfig = {
  enabled: false,
  days: [],
  time_ranges: [],
  auto_apply: { keyword: 'AI Agent', city: '淄博', daily_limit: 30, hr_active_filter: '在线,刚刚活跃,今日活跃,3日内活跃,本周活跃,本月活跃' },
  auto_reply: { style: 'professional' },
}

interface SchedulerStore {
  config: SchedulerConfig
  status: SchedulerStatus
  setConfig: (config: SchedulerConfig) => void
  updateConfig: (partial: Partial<SchedulerConfig>) => void
  setStatus: (status: SchedulerStatus) => void
  addExecutionLog: (entry: { time: string; tasks: string[] }) => void
}

export const useSchedulerStore = create<SchedulerStore>((set, get) => ({
  config: DEFAULT_CONFIG,
  status: { active: false, phase: 'idle', today_count: 0, daily_limit: 30, execution_log: [] },

  setConfig: (config) => set({ config }),

  updateConfig: (partial) =>
    set({ config: { ...get().config, ...partial } }),

  setStatus: (status) => set({ status }),

  addExecutionLog: (entry) =>
    set((state) => ({
      status: {
        ...state.status,
        execution_log: [entry, ...state.status.execution_log].slice(0, 20),
      },
    })),
}))
