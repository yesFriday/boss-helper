import { create } from 'zustand'
import type { SystemStatus } from '../api/types'

interface SystemState {
  browserRunning: boolean
  monitorRunning: boolean
  monitorPaused: boolean
  todayApplications: number
  sessionStatus: 'ok' | 'expired' | 'checking' | ''
  updateFromStatus: (data: SystemStatus) => void
  setSessionStatus: (s: SystemState['sessionStatus']) => void
}

export const useSystemStore = create<SystemState>((set) => ({
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
}))
