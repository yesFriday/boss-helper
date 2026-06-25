import { create } from 'zustand'
import type { Conversation, Message } from '../api/types'

interface ChatState {
  conversations: Conversation[]
  activeConvId: number | null
  messages: Message[]
  dangerFilter: boolean
  setConversations: (conversations: Conversation[]) => void
  setActiveConvId: (id: number | null) => void
  setMessages: (messages: Message[]) => void
  setDangerFilter: (enabled: boolean) => void
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  activeConvId: null,
  messages: [],
  dangerFilter: false,
  setConversations: (conversations) => set({ conversations }),
  setActiveConvId: (activeConvId) => set({ activeConvId }),
  setMessages: (messages) => set({ messages }),
  setDangerFilter: (dangerFilter) => set({ dangerFilter }),
}))
