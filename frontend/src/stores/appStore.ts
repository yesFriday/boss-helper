import { create } from 'zustand'

export type TabType = 'search' | 'applications' | 'chat' | 'wechat' | 'automation' | 'settings'

interface AppState {
  activeTab: TabType
  sidebarCollapsed: boolean
  setActiveTab: (tab: TabType) => void
  toggleSidebar: () => void
}

export const useAppStore = create<AppState>((set) => ({
  activeTab: 'search',
  sidebarCollapsed: false,
  setActiveTab: (tab) => set({ activeTab: tab }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}))
