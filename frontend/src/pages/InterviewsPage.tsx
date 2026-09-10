import { useState, useEffect, useMemo } from 'react'
import { CalendarDays, Video, MapPin, ExternalLink, ArrowDownAZ, ArrowUpAZ, Clock } from 'lucide-react'
import { Spinner } from '../components/common/Spinner'
import { useNotificationStore } from '../stores/notificationStore'
import { interviewsApi } from '../api/interviews'
import { systemApi } from '../api/system'
import type { Interview } from '../api/types'
import { cn } from '../lib/cn'

const INTERVIEW_TYPE_MAP: Record<string, { label: string; badgeClass: string }> = {
  online: { label: '线上', badgeClass: 'bg-sky-50 text-sky-700 border border-sky-200' },
  offline: { label: '线下', badgeClass: 'bg-violet-50 text-violet-700 border border-violet-200' },
}

const INTERVIEW_STATUS_MAP: Record<string, { label: string; badgeClass: string }> = {
  pending: { label: '待确认', badgeClass: 'bg-amber-50 text-amber-700 border border-amber-200' },
  confirmed: { label: '已确认', badgeClass: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
  done: { label: '已完成', badgeClass: 'bg-slate-100 text-slate-500 border border-slate-200' },
  cancelled: { label: '已取消', badgeClass: 'bg-slate-100 text-slate-400 border border-slate-200' },
}

const WEEKDAY_MAP = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export function InterviewsPage() {
  const { addToast } = useNotificationStore()
  const [interviews, setInterviews] = useState<Interview[]>([])
  const [loading, setLoading] = useState(true)
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => {
    interviewsApi.listInterviews()
      .then((res) => setInterviews(res.interviews || []))
      .catch(() => addToast('面试排期加载失败', 'error'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openJobUrl = (url: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!url) return
    systemApi.openUrl(url).catch(() => {
      window.open(url, '_blank', 'noopener,noreferrer')
    })
  }

  const sorted = useMemo(() => {
    const list = [...interviews]
    list.sort((a, b) => {
      const ka = `${a.interview_date} ${a.start_time}`
      const kb = `${b.interview_date} ${b.start_time}`
      return sortAsc ? ka.localeCompare(kb) : kb.localeCompare(ka)
    })
    return list
  }, [interviews, sortAsc])

  const today = new Date().toISOString().slice(0, 10)
  const upcoming = interviews.filter((it) => it.interview_date >= today).length
  const onlineCount = interviews.filter((it) => it.interview_type === 'online').length
  const offlineCount = interviews.filter((it) => it.interview_type === 'offline').length

  const formatTime = (it: Interview) => {
    const wd = it.interview_date ? WEEKDAY_MAP[new Date(`${it.interview_date}T00:00:00`).getDay()] : ''
    const start = (it.start_time || '').slice(11, 16) || it.start_time
    const end = (it.end_time || '').slice(11, 16) || it.end_time
    return `${it.interview_date} ${wd} ${start} - ${end}`
  }

  return (
    <div className="animate-slide-in">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          { label: '面试总数', value: interviews.length, accent: 'text-blue-600' },
          { label: '待面试', value: upcoming, accent: 'text-violet-600' },
          { label: '线上面试', value: onlineCount, accent: 'text-sky-600' },
          { label: '线下面试', value: offlineCount, accent: 'text-emerald-600' },
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
          <div className="text-sm font-medium text-slate-700">
            共 {interviews.length} 场面试
          </div>
          <button
            onClick={() => setSortAsc((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-500 hover:bg-white hover:text-slate-700 border border-transparent hover:border-slate-200 transition-colors cursor-pointer"
            title="切换时间排序"
          >
            <Clock size={13} />
            按时间{sortAsc ? '正序' : '倒序'}
            {sortAsc ? <ArrowUpAZ size={13} /> : <ArrowDownAZ size={13} />}
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/60">
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">面试岗位 (点击打开)</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">公司</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">面试时间</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">面试方式</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">地点/形式</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-slate-500">状态</th>
              </tr>
            </thead>
            <tbody>
              {!loading && sorted.length > 0 && sorted.map((it) => (
                <tr key={it.id} className="border-t border-slate-100 hover:bg-slate-50/70 transition-colors">
                  <td className="py-3 px-4">
                    {it.job_url ? (
                      <a
                        href={it.job_url}
                        onClick={(e) => openJobUrl(it.job_url!, e)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:text-blue-800 hover:underline font-medium inline-flex items-center gap-1.5 group cursor-pointer"
                        title="在浏览器中打开此岗位详情"
                      >
                        <span>{it.job_title || '未知岗位'}</span>
                        <ExternalLink size={12} className="text-blue-400 group-hover:text-blue-600 transition-colors" />
                      </a>
                    ) : (
                      <span className="text-slate-800 font-medium">{it.job_title || '未知岗位'}</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-slate-600">{it.company}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-1.5 text-slate-700">
                      <CalendarDays size={13} className="text-slate-400 flex-shrink-0" />
                      <span>{formatTime(it)}</span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium', (INTERVIEW_TYPE_MAP[it.interview_type] || INTERVIEW_TYPE_MAP.online).badgeClass)}>
                      {it.interview_type === 'offline' ? <MapPin size={11} /> : <Video size={11} />}
                      {(INTERVIEW_TYPE_MAP[it.interview_type] || INTERVIEW_TYPE_MAP.online).label}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-slate-600">
                    {it.interview_type === 'offline'
                      ? (it.location || '-')
                      : '视频 / 电话'}
                  </td>
                  <td className="py-3 px-4">
                    <span className={cn('inline-flex px-2 py-0.5 rounded-md text-xs font-medium', (INTERVIEW_STATUS_MAP[it.status] || { badgeClass: 'bg-slate-100 text-slate-500 border border-slate-200' }).badgeClass)}>
                      {INTERVIEW_STATUS_MAP[it.status]?.label || it.status}
                    </span>
                  </td>
                </tr>
              ))}
              {loading && (
                <tr><td colSpan={6} className="py-10 text-center"><Spinner size="md" /></td></tr>
              )}
              {!loading && sorted.length === 0 && (
                <tr><td colSpan={6} className="py-10 text-center text-slate-400">暂无面试安排</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
