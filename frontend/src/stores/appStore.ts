import { create } from 'zustand'

export type TabType = 'search' | 'applications' | 'chat' | 'wechat' | 'settings'

interface AppState {
  activeTab: TabType
  setActiveTab: (tab: TabType) => void
}

export const useAppStore = create<AppState>((set) => ({
  activeTab: 'search',
  setActiveTab: (tab) => set({ activeTab: tab }),
}))
