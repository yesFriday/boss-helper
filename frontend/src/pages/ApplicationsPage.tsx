import { useState, useEffect } from 'react'
import { Star, Send, ExternalLink } from 'lucide-react'
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
  const { appJobs, appCurrentPage, batchProgress } = useJobsStore()
  const { todayApplications } = useSystemStore()
  const { addToast } = useNotificationStore()
  const [filter, setFilter] = useState('')
  const [showShortlist, setShowShortlist] = useState(false)
  const [shortlists, setShortlists] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
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
  const interview = appJobs.filter((j) => j.status === 'interview').length

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
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="flex items-center justify-between p-4 flex-wrap gap-2 border-b border-slate-100">
          <div className="flex gap-1.5 flex-wrap">
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
                  filter === s.key && !showShortlist ? 'bg-blue-50 text-blue-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
                )}
              >
                {s.label}
              </button>
            ))}
            <div className="w-px bg-slate-200 mx-1" />
            <button
              onClick={loadShortlists}
              className={cn(
                'inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer',
                showShortlist ? 'bg-amber-50 text-amber-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
              )}
            >
              <Star size={12} className="mr-1" />
              收藏
            </button>
          </div>
          {!showShortlist && pending > 0 && (
            <Button variant="primary" size="sm" onClick={handleBatchApplyPending}>
              <Send size={13} />
              一键投递待投递 ({pending})
            </Button>
          )}
        </div>

        {batchProgress && (
          <div className="px-4 py-3 bg-blue-50/50 border-b border-blue-100">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium text-blue-700">投递进度</span>
              <span className="text-xs text-blue-600">{batchProgress.done}/{batchProgress.total} · {batchProgress.ok} 成功</span>
            </div>
            <div className="h-1.5 bg-blue-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-600 rounded-full transition-all duration-300"
                style={{ width: `${Math.round(batchProgress.done / batchProgress.total * 100)}%` }}
              />
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-400">岗位</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-400">公司</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-400">薪资</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-400">城市</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-400">HR活跃</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-400">状态</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-400 w-20">操作</th>
              </tr>
            </thead>
            <tbody>
              {showShortlist ? (
                shortlists.length > 0 ? (
                  shortlists.map((s) => (
                    <tr key={s.id} className="border-t border-slate-50 hover:bg-slate-50/50 transition-colors">
                      <td className="py-3 px-4">
                        <a href={s.job_url} target="_blank" rel="noopener noreferrer" className="text-slate-800 hover:text-blue-600 font-medium inline-flex items-center gap-1">
                          {s.job_title}
                          <ExternalLink size={11} className="text-slate-300" />
                        </a>
                      </td>
                      <td className="py-3 px-4 text-slate-600">{s.company}</td>
                      <td className="py-3 px-4 text-slate-900 font-medium">{s.salary}</td>
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
                      <td className="py-3 px-4"><span className="px-2 py-0.5 rounded-md text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">★ 收藏</span></td>
                      <td className="py-3 px-4">
                        <div className="flex gap-1.5">
                          <button onClick={() => handleRemoveShortlist(s.id)} className="text-xs text-slate-400 hover:text-red-500 transition-colors cursor-pointer px-1.5 py-1 rounded hover:bg-red-50">取消</button>
                          <button onClick={() => handleApply(s.job_url)} className="text-xs text-blue-600 font-medium hover:bg-blue-50 px-1.5 py-1 rounded transition-colors cursor-pointer">投递</button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={7} className="py-10 text-center text-slate-400">暂无收藏</td></tr>
                )
              ) : pageJobs.length > 0 ? (
                pageJobs.map((job) => (
                  <tr key={job.id || job.job_url} className="border-t border-slate-50 hover:bg-slate-50/50 transition-colors">
                    <td className="py-3 px-4">
                      {job.job_url ? (
                        <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="text-slate-800 hover:text-blue-600 font-medium inline-flex items-center gap-1">
                          {job.job_title || job.title || '未知'}
                          <ExternalLink size={11} className="text-slate-300" />
                        </a>
                      ) : (
                        <span className="text-slate-800 font-medium">{job.job_title || job.title || '未知'}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-600">{job.company}</td>
                    <td className="py-3 px-4 text-slate-900 font-medium">{job.salary}</td>
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
                      {job.status === 'pending' && job.job_url ? (
                        <button
                          onClick={() => handleApply(job.job_url)}
                          className="text-xs text-slate-400 hover:text-blue-600 transition-colors cursor-pointer px-1.5 py-1 rounded hover:bg-blue-50"
                        >
                          投递
                        </button>
                      ) : (
                        <span className="text-xs text-slate-300">-</span>
                      )}
                    </td>
                  </tr>
                ))
              ) : loading ? (
                <tr><td colSpan={7} className="py-10 text-center"><Spinner size="md" /></td></tr>
              ) : (
                <tr><td colSpan={7} className="py-10 text-center text-slate-400">暂无记录</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {!showShortlist && totalPages > 1 && (
          <div className="flex items-center justify-center gap-1 p-3 border-t border-slate-100">
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(1)}
              disabled={appCurrentPage <= 1}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >«</button>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(appCurrentPage - 1)}
              disabled={appCurrentPage <= 1}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >‹</button>
            <span className="text-xs text-slate-400 px-3">
              {appCurrentPage} / {totalPages}
            </span>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(appCurrentPage + 1)}
              disabled={appCurrentPage >= totalPages}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >›</button>
            <button
              onClick={() => useJobsStore.getState().setAppCurrentPage(totalPages)}
              disabled={appCurrentPage >= totalPages}
              className="px-2.5 py-1.5 rounded-lg text-xs text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >»</button>
          </div>
        )}
      </div>
    </div>
  )
}
