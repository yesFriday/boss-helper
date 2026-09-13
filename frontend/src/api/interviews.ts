import { api } from './client'
import type { ConflictedInterview, Interview } from './types'

export const interviewsApi = {
  listInterviews: () => api.get<{ interviews: Interview[] }>('/api/interviews'),
  removeInterview: (id: number) => api.del<{ success: boolean }>(`/api/interviews/${id}`),
  listConflicted: () => api.get<{ conflicted: ConflictedInterview[] }>('/api/interviews/conflicted'),
}
