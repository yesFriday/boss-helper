import { api } from './client'
import type { Settings } from './types'

export const settingsApi = {
  getSettings: () => api.get<{ settings: Settings }>('/api/settings'),
  updateSettings: (data: Partial<Settings>) => api.put('/api/settings', data),
  testAiSettings: (data: { ai_api_key?: string; ai_base_url?: string; ai_model?: string }) =>
    api.post<{ status: string; message: string }>('/api/settings/test-ai', data),
}
