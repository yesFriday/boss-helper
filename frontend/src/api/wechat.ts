import { api } from './client'
import type { WechatExchange } from './types'

export const wechatApi = {
  getWechatExchanges: () => api.get<{ exchanges: WechatExchange[] }>('/api/wechat-exchanges'),
}
