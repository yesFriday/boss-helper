import { create } from 'zustand'
import type { Settings } from '../api/types'

interface SettingsState {
  settings: Partial<Settings>
  aiKeyConfigured: boolean
  updateSettings: (s: Partial<Settings>) => void
  setAiKeyConfigured: (configured: boolean) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: {},
  aiKeyConfigured: false,
  updateSettings: (settings) => set({ settings }),
  setAiKeyConfigured: (aiKeyConfigured) => set({ aiKeyConfigured }),
}))
