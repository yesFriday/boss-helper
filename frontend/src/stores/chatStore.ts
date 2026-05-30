import { create } from 'zustand'
import type { Conversation, Message } from '../api/types'

interface ChatState {
  conversations: Conversation[]
  activeConvId: number | null
  messages: Message[]
  setConversations: (conversations: Conversation[]) => void
  setActiveConvId: (id: number | null) => void
  setMessages: (messages: Message[]) => void
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  activeConvId: null,
  messages: [],
  setConversations: (conversations) => set({ conversations }),
  setActiveConvId: (activeConvId) => set({ activeConvId }),
  setMessages: (messages) => set({ messages }),
}))
