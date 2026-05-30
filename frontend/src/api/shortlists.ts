import { api } from './client'
import type { Shortlist } from './types'

export const shortlistsApi = {
  listShortlists: () => api.get<{ shortlists: Shortlist[] }>('/api/shortlists'),
  addShortlist: (data: { job_url: string; title: string; company: string; salary: string; city: string }) =>
    api.post<{ status: string }>('/api/shortlists', data),
  removeShortlist: (id: number) => api.del(`/api/shortlists/${id}`),
}
