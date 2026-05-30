import { api } from './client'
import type { Settings } from './types'

export const settingsApi = {
  getSettings: () => api.get<{ settings: Settings }>('/api/settings'),
  updateSettings: (data: Partial<Settings>) => api.put('/api/settings', data),
}
