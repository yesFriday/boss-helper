import { useState } from 'react'
import { SearchBar } from '../components/search/SearchBar'
import { JobCard } from '../components/search/JobCard'
import { FunnelBar } from '../components/search/FunnelBar'
import { AnalyzeModal } from '../components/search/AnalyzeModal'
import { EmptyState } from '../components/common/EmptyState'
import { useJobsStore } from '../stores/jobsStore'
import { useSettingsStore } from '../stores/settingsStore'
import { useNotificationStore } from '../stores/notificationStore'
import { jobsApi } from '../api/jobs'
import { shortlistsApi } from '../api/shortlists'
import { systemApi } from '../api/system'
import type { Job, AnalyzeResult } from '../api/types'
import { Search, Square } from 'lucide-react'
import { cn } from '../lib/cn'

export function SearchPage() {
  const {
    searchJobs,
    searchInFlight,
    searchStatusMessage,
    funnel,
    batchProgress,
    isBatchApplying,
    batchCancelRequested,
    setIsBatchApplying,
    requestCancelBatchApply,
    resetCancelBatchApply,
    setBatchProgress,
  } = useJobsStore()
  const { settings } = useSettingsStore()
  const { addToast } = useNotificationStore()
  const [analyzeJob, setAnalyzeJob] = useState<Job | null>(null)
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResult | null>(null)
  const [analyzeLoading, setAnalyzeLoading] = useState(false)

  const handleSearch = async (keyword: string, city: string, welfare?: string, salaryExpect?: number, experienceExpect?: number, excludeHrActive?: string) => {
    useJobsStore.getState().setSearchInFlight(true)
    useJobsStore.getState().setSearchStatusMessage('<div class="flex items-center gap-2"><span class="animate-spin">⏳</span> 搜索中...</div>')
    try {
      const res = await jobsApi.searchJobs({ keyword, city, welfare, salary_expect: salaryExpect, experience_expect: experienceExpect, exclude_hr_active: excludeHrActive })
      useJobsStore.getState().setSearchStatusMessage(
        `<div class="text-emerald-600">找到 ${res.jobs_found} 条，已保存 ${res.saved} 条</div>`
      )
      if (res.jobs?.length) {
        useJobsStore.getState().setSearchJobs(res.jobs)
      } else {
        const jobs = await jobsApi.listJobs({ limit: 50 })
        useJobsStore.getState().setSearchJobs(jobs.jobs || [])
      }
    } catch (err: any) {
      useJobsStore.getState().setSearchStatusMessage(
        `<div class="text-red-500">失败: ${err.message}</div>`
      )
    } finally {
      useJobsStore.getState().setSearchInFlight(false)
    }
    const stats = await systemApi.getStats()
    useJobsStore.getState().setFunnel({
      pending: stats.pending || 0,
      today: stats.today_applications || 0,
      replied: stats.replied || 0,
      interview: stats.interview || 0,
    })
  }

  const handleBatchSearch = async () => {
    const keywords = (settings.search_keywords || '').split(',').filter(Boolean)
    if (keywords.length === 0) {
      handleSearch('AI Agent', '淄博')
      return
    }
    if (!confirm(`确定搜索 ${keywords.length} 个关键词？`)) return
    for (const kw of keywords) {
      await handleSearch(kw.trim(), '淄博')
    }
  }

  const handleBatchApply = async () => {
    if (isBatchApplying) return
    const pending = searchJobs.filter((j) => j.job_url && j.status !== 'applied' && j.status !== 'replied')
    if (!pending.length) {
      addToast('没有待投递的岗位，请先搜索', 'info')
      return
    }
    if (!confirm(`确定投递 ${pending.length} 条？`)) return

    setIsBatchApplying(true)
    resetCancelBatchApply()
    let done = 0, ok = 0
    setBatchProgress({ done: 0, ok: 0, total: pending.length, cancelled: false })

    for (const job of pending) {
      if (useJobsStore.getState().batchCancelRequested) {
        addToast(`批量投递已中断停止: ${ok}/${pending.length} 成功`, 'info')
        setBatchProgress({ done, ok, total: pending.length, cancelled: true })
        break
      }
      try {
        const res = await jobsApi.applyJob(job.job_url)
        if (res.success) {
          ok++
          useJobsStore.getState().updateJobStatus(job.job_url, 'applied')
        }
      } catch {}
      done++
      const isCancelled = useJobsStore.getState().batchCancelRequested
      setBatchProgress({ done, ok, total: pending.length, cancelled: isCancelled })
      if (isCancelled) {
        addToast(`批量投递已中断停止: ${ok}/${pending.length} 成功`, 'info')
        break
      }
    }

    if (!useJobsStore.getState().batchCancelRequested) {
      addToast(`批量投递完成: ${ok}/${pending.length} 成功`, 'success')
    }

    setIsBatchApplying(false)
    resetCancelBatchApply()
    const jobs = await jobsApi.listJobs({ limit: 50 })
    useJobsStore.getState().setSearchJobs(jobs.jobs || [])
    const stats = await systemApi.getStats()
    useJobsStore.getState().setFunnel({
      pending: stats.pending || 0,
      today: stats.today_applications || 0,
      replied: stats.replied || 0,
      interview: stats.interview || 0,
    })
  }

  const handleApply = async (url: string) => {
    try {
      const res = await jobsApi.applyJob(url)
      if (res.success) {
        useJobsStore.getState().updateJobStatus(url, 'applied')
        addToast('投递成功', 'success')
      } else {
        addToast(res.message || '投递失败', 'error')
      }
    } catch {
      addToast('投递失败', 'error')
    }
  }

  const handleAnalyze = async (job: Job) => {
    setAnalyzeJob(job)
    setAnalyzeLoading(true)
    setAnalyzeResult(null)
    try {
      const result = await jobsApi.analyzeJob({
        job_url: job.job_url,
        job_title: job.job_title || job.title || '',
        company: job.company || '',
        description: (job.description || '').slice(0, 500),
      })
      setAnalyzeResult(result)
    } catch (err: any) {
      setAnalyzeResult({ match_score: 0, key_skills: [], gap: '', advice: '', summary: '', error: err.message })
    } finally {
      setAnalyzeLoading(false)
    }
  }

  const handleCancelSearch = async () => {
    try {
      await jobsApi.cancelSearch()
      useJobsStore.getState().setSearchStatusMessage(
        '<div class="text-amber-600">搜索已停止</div>'
      )
    } catch {
      addToast('取消失败', 'error')
    }
  }

  const handleShortlist = async (job: Job) => {
    try {
      await shortlistsApi.addShortlist({
        job_url: job.job_url,
        title: job.job_title || job.title || '',
        company: job.company || '',
        salary: job.salary || '',
        city: job.city || '',
      })
      addToast('已收藏', 'success')
    } catch {
      addToast('收藏失败', 'error')
    }
  }

  return (
    <div className="animate-slide-in">
      <SearchBar
        onSearch={handleSearch}
        onBatchSearch={handleBatchSearch}
        onBatchApply={handleBatchApply}
        loading={searchInFlight}
        isBatchApplying={isBatchApplying}
      />

      {searchStatusMessage && (
        <div className="mb-4 p-3 bg-white rounded-xl border border-slate-200 text-sm flex items-center justify-between">
          <div dangerouslySetInnerHTML={{ __html: searchStatusMessage }} />
          {searchInFlight && (
            <button
              onClick={handleCancelSearch}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 border border-red-300 text-red-600 hover:bg-red-100 transition-colors cursor-pointer"
            >
              <Square size={12} />
              停止搜索
            </button>
          )}
        </div>
      )}

      {batchProgress && (
        <div className="mb-4 p-4 bg-blue-50/70 rounded-xl border border-blue-200">
          <div className="flex justify-between items-center mb-2.5">
            <div className="flex items-center gap-2">
              <span className={cn("inline-block w-2 h-2 rounded-full", isBatchApplying ? "bg-blue-600 animate-pulse" : "bg-emerald-500")} />
              <span className="text-sm font-semibold text-blue-900">
                {isBatchApplying ? '批量投递进行中' : batchProgress.cancelled ? '投递已中断' : '投递已完成'}
              </span>
              <span className="text-xs text-blue-700 ml-1">
                ({batchProgress.done}/{batchProgress.total} · {batchProgress.ok} 成功)
              </span>
            </div>
            {isBatchApplying && (
              <button
                onClick={requestCancelBatchApply}
                disabled={batchCancelRequested}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 border border-red-300 text-red-600 hover:bg-red-100 transition-colors cursor-pointer disabled:opacity-50"
              >
                <Square size={12} className="fill-red-600" />
                {batchCancelRequested ? '正在中断...' : '停止投递'}
              </button>
            )}
          </div>
          <div className="h-2 bg-blue-100 rounded-full overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all duration-300", batchProgress.cancelled ? "bg-amber-500" : "bg-blue-600")}
              style={{ width: `${Math.min(100, Math.round((batchProgress.done / batchProgress.total) * 100))}%` }}
            />
          </div>
        </div>
      )}

      {funnel.pending > 0 && (
        <FunnelBar {...funnel} />
      )}

      {searchJobs.length > 0 ? (
        <div className="flex flex-col gap-3">
          {searchJobs.map((job, i) => (
            <JobCard
              key={job.job_url || i}
              job={job}
              onApply={handleApply}
              onAnalyze={handleAnalyze}
              onShortlist={handleShortlist}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Search size={48} className="text-slate-300" />}
          title="点击搜索获取岗位"
          description="输入关键词和城市，开始搜索工作机会"
        />
      )}

      {analyzeJob && (
        <AnalyzeModal
          title={analyzeJob.job_title || analyzeJob.title || ''}
          company={analyzeJob.company || ''}
          result={analyzeResult}
          loading={analyzeLoading}
          onClose={() => setAnalyzeJob(null)}
        />
      )}
    </div>
  )
}