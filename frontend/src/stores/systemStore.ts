import { create } from 'zustand'
import type { SystemStatus } from '../api/types'
import { systemApi } from '../api/system'

interface SystemState {
  browserRunning: boolean
  monitorRunning: boolean
  monitorPaused: boolean
  todayApplications: number
  sessionStatus: 'ok' | 'expired' | 'checking' | ''
  updateFromStatus: (data: SystemStatus) => void
  setSessionStatus: (s: SystemState['sessionStatus']) => void
  toggleMonitor: () => Promise<void>
}

export const useSystemStore = create<SystemState>((set, get) => ({
  browserRunning: false,
  monitorRunning: false,
  monitorPaused: false,
  todayApplications: 0,
  sessionStatus: '',
  updateFromStatus: (data) =>
    set({
      browserRunning: data.browser_running,
      monitorRunning: data.monitor_running,
      monitorPaused: data.monitor_paused,
      todayApplications: data.today_applications,
    }),
  setSessionStatus: (sessionStatus) => set({ sessionStatus }),
  toggleMonitor: async () => {
    const { monitorPaused } = get()
    try {
      if (monitorPaused) {
        await systemApi.resumeMonitor()
        set({ monitorPaused: false })
      } else {
        await systemApi.pauseMonitor()
        set({ monitorPaused: true })
      }
    } catch (error) {
      console.error('切换监控状态失败:', error)
    }
  },
}))
