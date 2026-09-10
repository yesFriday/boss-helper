import { api } from './client'
import type { Interview } from './types'

export const interviewsApi = {
  listInterviews: () => api.get<{ interviews: Interview[] }>('/api/interviews'),
  removeInterview: (id: number) => api.del<{ success: boolean }>(`/api/interviews/${id}`),
}
