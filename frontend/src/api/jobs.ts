import { api } from './client'
import type { Job, AnalyzeResult } from './types'

export const jobsApi = {
  searchJobs: (data: { keyword: string; city: string; welfare?: string; salary_expect?: number; experience_expect?: number; exclude_hr_active?: string }) =>
    api.post<{ jobs_found: number; saved: number; jobs: Job[] }>('/api/jobs/search', data),

  cancelSearch: () => api.post<{ status: string }>('/api/jobs/search/cancel'),

  listJobs: (params?: { limit?: number; status?: string }) => {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', String(params.limit))
    if (params?.status) searchParams.set('status', params.status)
    return api.get<{ jobs: Job[] }>(`/api/jobs?${searchParams}`)
  },

  applyJob: (jobUrl: string) =>
    api.post<{ success: boolean; message?: string; application_id?: number }>('/api/jobs/apply', { job_url: jobUrl }),

  skipJob: (id: number) => api.post(`/api/jobs/${id}/skip`),

  analyzeJob: (data: { job_url: string; job_title: string; company: string; description: string }) =>
    api.post<AnalyzeResult>('/api/jobs/analyze', data),
}
