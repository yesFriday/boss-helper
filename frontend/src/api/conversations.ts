import { api } from './client'
import type { Conversation, Message } from './types'

export const conversationsApi = {
  listConversations: (filter?: string) =>
    api.get<{ conversations: Conversation[] }>(filter ? `/api/conversations?filter=${filter}` : '/api/conversations'),

  getMessages: (id: number, limit = 100) =>
    api.get<{ messages: Message[] }>(`/api/conversations/${id}/messages?limit=${limit}`),

  syncConversation: (id: number) =>
    api.post<{ messages: Message[] }>(`/api/conversations/${id}/sync`),

  sendMessage: (id: number, content: string) =>
    api.post(`/api/conversations/${id}/send`, { content }),

  toggleAutoReply: (id: number, enabled: boolean) =>
    api.post(`/api/conversations/${id}/auto-reply`, { enabled }),
}
