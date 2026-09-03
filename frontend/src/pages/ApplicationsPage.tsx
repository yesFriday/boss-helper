import { useState, useEffect } from 'react'
import { Star, Send, ExternalLink, Square, Trash2 } from 'lucide-react'
import { Spinner } from '../components/common/Spinner'
import { Button } from '../components/common/Button'
import { useJobsStore } from '../stores/jobsStore'
import { useSystemStore } from '../stores/systemStore'
import { useNotificationStore } from '../stores/notificationStore'
import { jobsApi } from '../api/jobs'
import { shortlistsApi } from '../api/shortlists'
import { systemApi } from '../api/system'
import { STATUS_MAP, STATUS_BADGE_CLASS, HR_ACTIVE_BADGE_CLASS } from '../lib/constants'
import { cn } from '../lib/cn'

const PAGE_SIZE = 20

export function ApplicationsPage() {
  const {
    appJobs,
    appCurrentPage,
    batchProgress,
    isBatchApplying,
    batchCancelRequested,
    setIsBatchApplying,
    requestCancelBatchApply,
    resetCancelBatchApply,
    setBatchProgress,
  } = useJobsStore()
  const { todayApplications } = useSystemStore()
  const { addToast } = useNotificationStore()
  const [filter, setFilter] = useState('')
  const [showShortlist, setShowShortlist] = useState(false)
  const [shortlists, setShortlists] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  useEffect(() => {
    setSelectedIds([])
    loadApplications()
  }, [filter])

  const loadApplications = async () => {
    setLoading(true)
    try {
      const res = await jobsApi.listJobs({ limit: 500, status: filter || undefined })
      useJobsStore.getState().setAppJobs(res.jobs || [])
    } catch {} finally { setLoading(false) }
    const stats = await systemApi.getStats()
    useJobsStore.getState().setFunnel({
      pending: stats.pending || 0,
      today: stats.today_applications || 0,
      replied: stats.replied || 0,
      interview: stats.interview || 0,
    })
  }

  const loadShortlists = async () => {
    try {
      const res = await shortlistsApi.listShortlists()
      setShortlists(res.shortlists || [])
      setShowShortlist(true)
      setSelectedIds([])
    } catch {}
  }

  const handleApply = async (url: string) => {
    try {
      const res = await jobsApi.applyJob(url)
      if (res.success) {
        addToast('投递成功', 'success')
        loadApplications()
      } else {
        addToast(res.message || '投递失败', 'error')
      }
    } catch {
      addToast('投递失败', 'error')
    }
  }

  const handleRemoveShortlist = async (id: number) => {
    await shortlistsApi.removeShortlist(id)
    loadShortlists()
  }

  const handleDeleteSingle = async (jobId: number, jobTitle?: string) => {
    if (!confirm(`确定删除岗位「${jobTitle || '此岗位'}」的记录？`)) return
    try {
      await jobsApi.deleteJob(jobId)
      addToast('已删除记录', 'success')
      setSelectedIds((prev) => prev.filter((id) => id !== jobId))
      loadApplications()
    } catch {
      addToast('删除失败', 'error')
    }
  }

  const handleDeleteBatch = async () => {
    if (!selectedIds.length) return
    if (!confirm(`确定删除选中的 ${selectedIds.length} 条岗位记录？`)) return
    try {
      await jobsApi.deleteJobsBatch(selectedIds)
      addToast(`成功删除 ${selectedIds.length} 条岗位记录`, 'success')
      setSelectedIds([])
      loadApplications()
    } catch {
      addToast('批量删除失败', 'error')
    }
  }

  const handleBatchApplyPending = async () => {
    if (isBatchApplying) return
    try {
      const res = await jobsApi.listJobs({ limit: 200, status: 'pending' })
      const pending = (res.jobs || []).filter((j) => j.job_url)
      if (!pending.length) {
        addToast('没有待投递岗位', 'info')
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
          const r = await jobsApi.applyJob(job.job_url)
          if (r.success) ok++
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
      loadApplications()
    } catch {
      setIsBatchApplying(false)
      resetCancelBatchApply()
    }
  }

  const openJobUrl = (url: string, e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    if (!url) return
    systemApi.openUrl(url).catch(() => {
      window.open(url, '_blank', 'noopener,noreferrer')
    })
  }

  const totalPages = Math.max(1, Math.ceil(appJobs.length / PAGE_SIZE))
  const pageJobs = appJobs.slice((appCurrentPage - 1) * PAGE_SIZE, appCurrentPage * PAGE_SIZE)
  const pending = appJobs.filter((j) => j.status === 'pending').length
  const replied = appJobs.filter((j) => j.status === 'replied').length
  const interview = appJobs.filter((j) => j.status === 'interview').length

  const currentPageIds = pageJobs.map((j) => j.id).filter(Boolean) as number[]
  const isAllSelected = currentPageIds.length > 0 && currentPageIds.every((id) => selectedIds.includes(id))

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedIds((prev) => prev.filter((id) => !currentPageIds.includes(id)))
    } else {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...currentPageIds])))
    }
  }

  const toggleSelectOne = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  return (
    <div className="animate-slide-in">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          { label: '今日投递', value: todayApplications, accent: 'text-blue-600' },
          { label: '待投递', value: pending, accent: 'text-amber-600' },
          { label: 'HR已回复', value: replied, accent: 'text-emerald-600' },
          { label: '面试邀请', value: interview, accent: 'text-violet-600' },
        ].map((item) => (
          <div key={item.label} className="rounded-xl bg-white border border-slate-200 p-4">
            <div className={cn('text-2xl font-semibold', item.accent)}>{item.value}</div>
            <div className="text-xs text-slate-400 mt-1">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Table card */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        <div className="flex items-center justify-between p-4 flex-wrap gap-3 border-b border-slate-100 bg-slate-50/50">
          <div className="flex gap-1.5 flex-wrap items-center">
            {[
              { key: '', label: '全部' },
              { key: 'pending', label: '待投递' },
              { key: 'applied', label: '已投递' },
              { key: 'replied', label: '已回复' },
            ].map((s) => (
              <button
                key={s.key}
                onClick={() => { setFilter(s.key); setShowShortlist(false) }}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer',
                  filter === s.key && !showShortlist ? 'bg-blue-50 text-blue-700 font-semibold' : 'text-slate-500 hover:bg-white hover:text-slate-700'
                )}
              >
                {s.label}
              </button>
            ))}
            <div className="w-px h-4 bg-slate-200 mx-1" />
            <button
              onClick={loadShortlists}
              className={cn(
                'inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer',
                showShortlist ? 'bg-amber-50 text-amber-700 font-semibold border border-amber-200' : 'text-slate-500 hover:bg-white hover:text-slate-700'
              )}
            >
              <Star size={12} className="mr-1 fill-amber-500 text-amber-500" />
              收藏
            </button>
          </div>

          <div className="flex items-center gap-2">
            {!showShortlist && selectedIds.length > 0 && (
              <div className="flex items-center gap-2 mr-1">
                <span className="text-xs text-slate-500">已选中 {selectedIds.length} 项</span>
                <button
                  onClick={handleDeleteBatch}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 transition-colors cursor-pointer shadow-xs"
                >
                  <Trash2 size={13} />
                  批量删除 ({selectedIds.length})
                </button>
              </div>
            )}

            {!showShortlist && pending > 0 && (
              <Button variant="primary" size="sm" onClick={handleBatchApplyPending} disabled={isBatchApplying}>
                <Send size={13} className={cn(isBatchApplying && 'animate-pulse')} />
                {isBatchApplying ? '投递中...' : `一键投递待投递 (${pending})`}
              </Button>
            )}
          </div>
        </div>

        {batchProgress && (
          <div className="px-4 py-3.5 bg-blue-50/70 border-b border-blue-100">
            <div className="flex justify-between items-center mb-2">
              <div className="flex items-center gap-2">
                <span className={cn("inline-block w-2 h-2 rounded-full", isBatchApplying ? "bg-blue-600 animate-pulse" : "bg-emerald-500")} />
                <span className="text-sm font-medium text-blue-900">
                  {isBatchApplying ? '投递进度' : batchProgress.cancelled ? '投递已中断' : '投递已完成'}
                </span>
                <span className="text-xs text-blue-700 font-medium ml-1">
                  {batchProgress.done}/{batchProgress.total} · {batchProgress.ok} 成功
                </span>
              </div>
              {isBatchApplying && (
                <button
                  onClick={requestCancelBatchApply}
                  disabled={batchCancelRequested}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-red-50 border border-red-300 text-red-600 hover:bg-red-100 transition-colors cursor-pointer disabled:opacity-50"
                >
                  <Square size={11} className="fill-red-600" />
                  {batchCancelRequested ? '正在停止...' : '停止投递'}
                </button>
              )}
            </div>
            <div className="h-1.5 bg-blue-100 rounded-full overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all duration-300", batchProgress.cancelled ? "bg-amber-500" : "bg-blue-600")}
                style={{ width: `${Math.min(100, Math.round((batchProgress.done / batchProgress.total) * 100))}%` }}
              />
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/60">
                {!showShortlist && (
                  <th className="w-10 py-2.5 px-3 text-center">
                    <input
                      type="checkbox"
                      checked={isAllSelected}
                      onChange={toggleSelectAll}
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                      title="全选当页"
                    />
                  </th>
                )}
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">岗位名称 (点击打开)</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">公司</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">薪资</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">城市</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">HR活跃</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">状态</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500 w-28">操作</th>
              </tr>
            </thead>
            <tbody>
              {showShortlist ? (
                shortlists.length > 0 ? (
                  shortlists.map((s) => (
                    <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-4">
                        <a
                          href={s.job_url}
                          onClick={(e) => openJobUrl(s.job_url, e)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 hover:underline font-medium inline-flex items-center gap-1.5 group cursor-pointer"
                          title="在浏览器中打开此岗位"
                        >
                          <span>{s.job_title}</span>
                          <ExternalLink size={12} className="text-blue-400 group-hover:text-blue-600 transition-colors" />
                        </a>
                      </td>
                      <td className="py-3 px-4 text-slate-600">{s.company}</td>
                      <td className="py-3 px-4 text-slate-900 font-semibold">{s.salary}</td>
                      <td className="py-3 px-4 text-slate-600">{s.city}</td>
                      <td className="py-3 px-4">
                        {s.hr_active_time ? (
                          <span className={cn('px-2 py-0.5 rounded-md text-xs font-medium border', HR_ACTIVE_BADGE_CLASS[s.hr_active_time] || 'bg-gray-50 text-gray-500 border-gray-200')}>
                            {s.hr_active_time}
                          </span>
                        ) : (
                          <span className="text-xs text-slate-300">-</span>
                        )}
                      </td>
                      <td className="py-3 px-4"><span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200"><Star size={11} className="mr-1 fill-amber-500 text-amber-500" />收藏</span></td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          <button onClick={() => handleApply(s.job_url)} className="text-xs text-blue-600 font-medium hover:bg-blue-50 px-2 py-1 rounded transition-colors cursor-pointer">投递</button>
                          <button onClick={() => handleRemoveShortlist(s.id)} className="text-xs text-slate-400 hover:text-red-500 hover:bg-red-50 px-2 py-1 rounded transition-colors cursor-pointer" title="取消收藏">取消</button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={7} className="py-10 text-center text-slate-400">暂无收藏记录</td></tr>
                )
              ) : pageJobs.length > 0 ? (
                pageJobs.map((job) => (
                  <tr
                    key={job.id || job.job_url}
                    className={cn(
                      'border-t border-slate-100 hover:bg-slate-50/70 transition-colors',
                      job.id && selectedIds.includes(job.id) && 'bg-blue-50/30'
                    )}
                  >
                    <td className="py-3 px-3 text-center">
                      {job.id ? (
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(job.id)}
                          onChange={() => toggleSelectOne(job.id!)}
                          className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                        />
                      ) : (
                        <span className="text-xs text-slate-300">-</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {job.job_url ? (
                        <a
                          href={job.job_url}
                          onClick={(e) => openJobUrl(job.job_url, e)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 hover:underline font-medium inline-flex items-center gap-1.5 group cursor-pointer"
                          title="在浏览器中打开此岗位详情"
                        >
                          <span>{job.job_title || job.title || '未知岗位'}</span>
                          <ExternalLink size={12} className="text-blue-400 group-hover:text-blue-600 transition-colors" />
                        </a>
                      ) : (
                        <span className="text-slate-800 font-medium">{job.job_title || job.title || '未知岗位'}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-600">{job.company}</td>
                    <td className="py-3 px-4 text-slate-900 font-semibold">{job.salary}</td>
                    <td className="py-3 px-4 text-slate-600">{job.city}</td>
                    <td className="py-3 px-4">
                      {job.hr_active_time ? (
                        <span className={cn('px-2 py-0.5 rounded-md text-xs font-medium border', HR_ACTIVE_BADGE_CLASS[job.hr_active_time] || 'bg-gray-50 text-gray-500 border-gray-200')}>
                          {job.hr_active_time}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-300">-</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <span className={cn('rounded-md px-2 py-0.5 text-xs font-medium', STATUS_BADGE_CLASS[job.status || 'pending'])}>
                        {STATUS_MAP[job.status || 'pending']}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5">
                        {job.status === 'pending' && job.job_url && (
                          <button
                            onClick={() => handleApply(job.job_url)}
                            className="text-xs text-blue-600 font-medium hover:bg-blue-50 px-2 py-1 rounded transition-colors cursor-pointer"
                          >
                            投递
                          </button>
                        )}
                        {job.id && (
                          <button
                            onClick={() => handleDeleteSingle(job.id!, job.job_title || job.title)}
                            className="text-xs text-slate-400 hover:text-red-600 hover:bg-red-50 p-1.5 rounded transition-colors cursor-pointer"
                            title="删除此条记录"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              ) : loading ? (
                <tr><td colSpan={8} className="py-10 text-center"><Spinner size="md" /></td></tr>
              ) : (
                <tr><td colSpan={8} className="py-10 text-center text-slate-400">暂无记录</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {!showShortlist && totalPages > 1 && (
          <div className="flex items-center justify-center gap-1 p-3 border-t border-slate-100 bg-slate-50/30">
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(1)}
              disabled={appCurrentPage <= 1}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >«</button>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(appCurrentPage - 1)}
              disabled={appCurrentPage <= 1}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >‹</button>
            <span className="text-xs text-slate-500 px-3 font-medium">
              {appCurrentPage} / {totalPages}
            </span>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(appCurrentPage + 1)}
              disabled={appCurrentPage >= totalPages}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >›</button>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(totalPages)}
              disabled={appCurrentPage >= totalPages}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >»</button>
          </div>
        )}
      </div>
    </div>
  )
}
