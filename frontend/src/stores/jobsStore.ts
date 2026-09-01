import { create } from 'zustand'
import type { Job, BatchProgress } from '../api/types'

interface JobsState {
  searchJobs: Job[]
  appJobs: Job[]
  searchInFlight: boolean
  searchStatusMessage: string
  funnel: { pending: number; today: number; replied: number; interview: number }
  appCurrentPage: number
  batchProgress: BatchProgress | null
  isBatchApplying: boolean
  batchCancelRequested: boolean
  setSearchJobs: (jobs: Job[]) => void
  setAppJobs: (jobs: Job[]) => void
  setSearchInFlight: (inFlight: boolean) => void
  setSearchStatusMessage: (msg: string) => void
  updateJobStatus: (url: string, status: string) => void
  setFunnel: (f: JobsState['funnel']) => void
  setAppCurrentPage: (page: number) => void
  setBatchProgress: (progress: BatchProgress | null) => void
  setIsBatchApplying: (applying: boolean) => void
  requestCancelBatchApply: () => void
  resetCancelBatchApply: () => void
}

export const useJobsStore = create<JobsState>((set) => ({
  searchJobs: [],
  appJobs: [],
  searchInFlight: false,
  searchStatusMessage: '',
  funnel: { pending: 0, today: 0, replied: 0, interview: 0 },
  appCurrentPage: 1,
  batchProgress: null,
  isBatchApplying: false,
  batchCancelRequested: false,
  setSearchJobs: (searchJobs) => set({ searchJobs }),
  setAppJobs: (appJobs) => set({ appJobs }),
  setSearchInFlight: (searchInFlight) => set({ searchInFlight }),
  setSearchStatusMessage: (searchStatusMessage) => set({ searchStatusMessage }),
  updateJobStatus: (url, status) =>
    set((state) => ({
      searchJobs: state.searchJobs.map((j) =>
        j.job_url === url ? { ...j, status: status as Job['status'] } : j
      ),
    })),
  setFunnel: (funnel) => set({ funnel }),
  setAppCurrentPage: (appCurrentPage) => set({ appCurrentPage }),
  setBatchProgress: (batchProgress) => set({ batchProgress }),
  setIsBatchApplying: (isBatchApplying) => set({ isBatchApplying }),
  requestCancelBatchApply: () => set({ batchCancelRequested: true }),
  resetCancelBatchApply: () => set({ batchCancelRequested: false }),
}))
