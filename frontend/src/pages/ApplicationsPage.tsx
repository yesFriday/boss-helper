import { useState, useEffect } from 'react'
import { Star, Send } from 'lucide-react'
import { useJobsStore } from '../stores/jobsStore'
import { useSystemStore } from '../stores/systemStore'
import { useNotificationStore } from '../stores/notificationStore'
import { jobsApi } from '../api/jobs'
import { shortlistsApi } from '../api/shortlists'
import { systemApi } from '../api/system'
import { STATUS_MAP, STATUS_BADGE_CLASS } from '../lib/constants'
import { cn } from '../lib/cn'

const PAGE_SIZE = 15

export function ApplicationsPage() {
  const { appJobs, appCurrentPage, batchProgress } = useJobsStore()
  const { todayApplications } = useSystemStore()
  const { addToast } = useNotificationStore()
  const [filter, setFilter] = useState('')
  const [showShortlist, setShowShortlist] = useState(false)
  const [shortlists, setShortlists] = useState<any[]>([])

  useEffect(() => {
    loadApplications()
  }, [filter])

  const loadApplications = async () => {
    try {
      const res = await jobsApi.listJobs({ limit: 500, status: filter || undefined })
      useJobsStore.getState().setAppJobs(res.jobs || [])
    } catch {}
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

  const handleBatchApplyPending = async () => {
    try {
      const res = await jobsApi.listJobs({ limit: 200, status: 'pending' })
      const pending = (res.jobs || []).filter((j) => j.job_url)
      if (!pending.length) {
        addToast('没有待投递岗位', 'info')
        return
      }
      if (!confirm(`确定投递 ${pending.length} 条？`)) return
      let done = 0, ok = 0
      useJobsStore.getState().setBatchProgress({ done: 0, ok: 0, total: pending.length, cancelled: false })
      for (const job of pending) {
        try {
          const r = await jobsApi.applyJob(job.job_url)
          if (r.success) ok++
        } catch {}
        done++
        useJobsStore.getState().setBatchProgress({ done, ok, total: pending.length, cancelled: false })
      }
      useJobsStore.getState().setBatchProgress(null)
      loadApplications()
      addToast(`批量投递完成: ${ok}/${pending.length} 成功`, 'success')
    } catch {}
  }

  const totalPages = Math.max(1, Math.ceil(appJobs.length / PAGE_SIZE))
  const pageJobs = appJobs.slice((appCurrentPage - 1) * PAGE_SIZE, appCurrentPage * PAGE_SIZE)
  const pending = appJobs.filter((j) => j.status === 'pending').length
  const replied = appJobs.filter((j) => j.status === 'replied').length

  return (
    <div className="animate-slide-in">
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: '今日投递', value: todayApplications, color: 'from-indigo-400 to-purple-400' },
          { label: '待投递', value: pending, color: 'from-amber-400 to-orange-400' },
          { label: 'HR已回复', value: replied, color: 'from-emerald-400 to-teal-400' },
          { label: '每日上限', value: 15, color: 'from-pink-400 to-rose-400' },
        ].map((item) => (
          <div key={item.label} className="bg-white rounded-xl p-5 text-center shadow-sm border border-slate-200 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
            <div className={cn('text-3xl font-extrabold bg-gradient-to-r bg-clip-text text-transparent', item.color)}>
              {item.value}
            </div>
            <div className="text-xs text-slate-400 mt-1 font-semibold uppercase tracking-wider">{item.label}</div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-200">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex gap-2">
            {['', 'pending', 'applied', 'replied'].map((s) => (
              <button
                key={s}
                onClick={() => { setFilter(s); setShowShortlist(false) }}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer',
                  filter === s && !showShortlist ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                )}
              >
                {s ? STATUS_MAP[s] : '全部'}
              </button>
            ))}
            <button
              onClick={loadShortlists}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer',
                showShortlist ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              )}
            >
              <Star size={12} className="inline mr-1" />
              收藏
            </button>
          </div>
          <button
            onClick={handleBatchApplyPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-500 shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
          >
            <Send size={14} />
            一键投递待投递
          </button>
        </div>

        {batchProgress && (
          <div className="mb-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
            <div className="flex justify-between items-center mb-2">
              <span className="font-semibold text-sm">投递进度</span>
              <span className="text-xs text-slate-500">{batchProgress.done}/{batchProgress.total} ({batchProgress.ok} 成功)</span>
            </div>
            <div className="h-3 bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-300"
                style={{ width: `${Math.round(batchProgress.done / batchProgress.total * 100)}%` }}
              />
            </div>
            <div className="text-xs text-indigo-600 font-semibold mt-1">
              {Math.round(batchProgress.done / batchProgress.total * 100)}%
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50">
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">岗位</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">公司</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">薪资</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">城市</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">状态</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">操作</th>
              </tr>
            </thead>
            <tbody>
              {showShortlist ? (
                shortlists.length > 0 ? (
                  shortlists.map((s) => (
                    <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="py-3 px-4">
                        <a href={s.job_url} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline font-medium">
                          {s.job_title}
                        </a>
                      </td>
                      <td className="py-3 px-4 text-slate-600">{s.company}</td>
                      <td className="py-3 px-4 text-red-500 font-semibold">{s.salary}</td>
                      <td className="py-3 px-4 text-slate-600">{s.city}</td>
                      <td className="py-3 px-4"><span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full text-xs font-semibold">收藏</span></td>
                      <td className="py-3 px-4">
                        <div className="flex gap-2">
                          <button onClick={() => handleRemoveShortlist(s.id)} className="px-2.5 py-1 rounded-lg text-xs bg-slate-100 text-slate-600 hover:bg-slate-200 cursor-pointer">取消</button>
                          <button onClick={() => handleApply(s.job_url)} className="px-2.5 py-1 rounded-lg text-xs bg-indigo-500 text-white hover:bg-indigo-600 cursor-pointer">投递</button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={6} className="py-8 text-center text-slate-400">暂无收藏</td></tr>
                )
              ) : pageJobs.length > 0 ? (
                pageJobs.map((job) => (
                  <tr key={job.id || job.job_url} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="py-3 px-4">
                      <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline font-medium">
                        {job.job_title || job.title || '未知'}
                      </a>
                    </td>
                    <td className="py-3 px-4 text-slate-600">{job.company}</td>
                    <td className="py-3 px-4 text-red-500 font-semibold">{job.salary}</td>
                    <td className="py-3 px-4 text-slate-600">{job.city}</td>
                    <td className="py-3 px-4">
                      <span className={cn('px-2 py-0.5 rounded-full text-xs font-semibold', STATUS_BADGE_CLASS[job.status || 'pending'])}>
                        {STATUS_MAP[job.status || 'pending']}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {job.job_url && (
                        <button onClick={() => handleApply(job.job_url)} className="px-2.5 py-1 rounded-lg text-xs bg-indigo-500 text-white hover:bg-indigo-600 cursor-pointer">
                          投递
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={6} className="py-8 text-center text-slate-400">暂无记录</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {!showShortlist && totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-4">
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(1)}
              disabled={appCurrentPage <= 1}
              className="px-3 py-1.5 rounded-lg text-xs bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 cursor-pointer"
            >
              «
            </button>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(appCurrentPage - 1)}
              disabled={appCurrentPage <= 1}
              className="px-3 py-1.5 rounded-lg text-xs bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 cursor-pointer"
            >
              ‹
            </button>
            <span className="text-xs text-slate-400 px-3">
              {(appCurrentPage - 1) * PAGE_SIZE + 1}-{Math.min(appCurrentPage * PAGE_SIZE, appJobs.length)} / {appJobs.length}
            </span>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(appCurrentPage + 1)}
              disabled={appCurrentPage >= totalPages}
              className="px-3 py-1.5 rounded-lg text-xs bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 cursor-pointer"
            >
              ›
            </button>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(totalPages)}
              disabled={appCurrentPage >= totalPages}
              className="px-3 py-1.5 rounded-lg text-xs bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 cursor-pointer"
            >
              »
            </button>
          </div>
        )}
      </div>
    </div>
  )
}