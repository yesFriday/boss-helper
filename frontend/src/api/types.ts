export interface Job {
  id?: number
  job_title: string
  title?: string
  company: string
  salary: string
  job_url: string
  city: string
  experience: string
  education: string
  hr_name: string
  hr_title: string
  description: string
  status: 'pending' | 'applied' | 'replied' | 'skipped' | 'failed' | 'missing_url'
}

export interface Conversation {
  id: number
  application_id: number
  hr_name: string
  hr_company: string
  job_title: string
  last_message_text: string
  last_message_from: string
  last_message_at: string
  unread_count: number
  status: string
  auto_reply_enabled: number
  interest_level: string
  hr_wechat: string
  wechat_shared_at: string
  resume_sent: number
  phone_shared: number
}

export interface Message {
  id: number
  conversation_id: number
  sender: 'me' | 'hr'
  content: string
  ai_generated: number
  created_at: string
  delivery_status?: string
}

export interface SystemStatus {
  browser_running: boolean
  auto_reply_enabled: boolean
  monitor_running: boolean
  monitor_paused: boolean
  today_applications: number
  active_conversations: number
  daily_stats: Record<string, number>
}

export interface FunnelStats {
  today_applications: number
  pending: number
  replied: number
  interview: number
  active_conversations: number
  daily_stats: Record<string, number>
}

export interface WSMessage {
  type: string
  [key: string]: unknown
}

export interface Settings {
  greeting_template: string
  ai_reply_style: string
  daily_apply_limit: string
  min_reply_delay_sec: string
  max_reply_delay_sec: string
  resume_summary: string
  wechat_id: string
  search_keywords: string
  auto_reply_enabled: string
  ai_base_url: string
  ai_model: string
  ai_key_configured: string
}

export interface AnalyzeResult {
  match_score: number
  key_skills: string[]
  gap: string
  advice: string
  summary: string
  error?: string
}

export interface WechatExchange {
  hr_name: string
  hr_company: string
  hr_wechat: string
  wechat_shared_at: string
  job_description: string
  job_title: string
}

export interface Shortlist {
  id: number
  job_url: string
  job_title: string
  company: string
  salary: string
  city: string
}

export interface BatchProgress {
  done: number
  ok: number
  total: number
  cancelled: boolean
}
