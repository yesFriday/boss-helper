import { useState, useEffect, useMemo } from 'react'
import { CalendarDays, Video, MapPin, ExternalLink, ArrowDownAZ, ArrowUpAZ, Clock, AlertTriangle, RotateCcw } from 'lucide-react'
import { Spinner } from '../components/common/Spinner'
import { useNotificationStore } from '../stores/notificationStore'
import { interviewsApi } from '../api/interviews'
import { systemApi } from '../api/system'
import type { ConflictedInterview, Interview } from '../api/types'
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

const inputCls = "rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none transition-colors placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15"

const EMPTY_FILTER = { keyword: '', type: 'all', status: 'all', dateFrom: '', dateTo: '' }

type FilterState = typeof EMPTY_FILTER

function matchText(fields: (string | null | undefined)[], keyword: string) {
  const kw = keyword.trim().toLowerCase()
  if (!kw) return true
  return fields.some((f) => (f || '').toLowerCase().includes(kw))
}

function matchDate(date: string | null | undefined, f: FilterState) {
  if (!date) return true
  if (f.dateFrom && date < f.dateFrom) return false
  if (f.dateTo && date > f.dateTo) return false
  return true
}

export function InterviewsPage() {
  const { addToast } = useNotificationStore()
  const [tab, setTab] = useState<'normal' | 'conflict'>('normal')
  const [interviews, setInterviews] = useState<Interview[]>([])
  const [conflicted, setConflicted] = useState<ConflictedInterview[]>([])
  const [loading, setLoading] = useState(true)
  const [sortAsc, setSortAsc] = useState(true)
  const [filter, setFilter] = useState<FilterState>(EMPTY_FILTER)

  useEffect(() => {
    Promise.all([interviewsApi.listInterviews(), interviewsApi.listConflicted()])
      .then(([normal, conflict]) => {
        setInterviews(normal.interviews || [])
        setConflicted(conflict.conflicted || [])
      })
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

  const setF = (patch: Partial<FilterState>) => setFilter((prev) => ({ ...prev, ...patch }))
  const hasFilter = filter.keyword || filter.type !== 'all' || filter.status !== 'all' || filter.dateFrom || filter.dateTo

  const filteredNormal = useMemo(() => {
    const list = interviews.filter((it) =>
      matchText([it.job_title, it.company], filter.keyword) &&
      matchDate(it.interview_date, filter) &&
      (filter.type === 'all' || it.interview_type === filter.type) &&
      (filter.status === 'all' || it.status === filter.status)
    )
    list.sort((a, b) => {
      const ka = `${a.interview_date} ${a.start_time}`
      const kb = `${b.interview_date} ${b.start_time}`
      return sortAsc ? ka.localeCompare(kb) : kb.localeCompare(ka)
    })
    return list
  }, [interviews, filter, sortAsc])

  const filteredConflicted = useMemo(() => {
    const list = conflicted.filter((c) =>
      matchText([c.job_title, c.company, c.hr_name, c.hr_message, c.conflict_reason], filter.keyword) &&
      matchDate(c.interview_date, filter) &&
      (filter.type === 'all' || c.interview_type === filter.type)
    )
    list.sort((a, b) => `${b.interview_date} ${b.start_time}`.localeCompare(`${a.interview_date} ${a.start_time}`))
    return list
  }, [conflicted, filter])

  // 本地日期（toISOString 返回 UTC，北京时间 0-8 点会错拿昨天的日期）
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const upcoming = interviews.filter((it) => it.interview_date >= today).length
  const onlineCount = interviews.filter((it) => it.interview_type === 'online').length
  const offlineCount = interviews.filter((it) => it.interview_type === 'offline').length

  const formatTime = (date: string | null, start: string | null, end: string | null) => {
    if (!date && !start) return '-'
    const wd = date ? WEEKDAY_MAP[new Date(`${date}T00:00:00`).getDay()] : ''
    const s = (start || '').slice(11, 16) || start || ''
    const e = (end || '').slice(11, 16) || end || ''
    return `${date || ''} ${wd} ${s}${e ? ' - ' + e : ''}`.trim()
  }

  const renderJobCell = (title: string | null, url: string | null | undefined) =>
    url ? (
      <a
        href={url}
        onClick={(e) => openJobUrl(url, e)}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-600 hover:text-blue-800 hover:underline font-medium inline-flex items-center gap-1.5 group cursor-pointer"
        title="在浏览器中打开此岗位详情"
      >
        <span>{title || '未知岗位'}</span>
        <ExternalLink size={12} className="text-blue-400 group-hover:text-blue-600 transition-colors" />
      </a>
    ) : (
      <span className="text-slate-800 font-medium">{title || '未知岗位'}</span>
    )

  const renderTypeBadge = (type: string) => (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium', (INTERVIEW_TYPE_MAP[type] || INTERVIEW_TYPE_MAP.online).badgeClass)}>
      {type === 'offline' ? <MapPin size={11} /> : <Video size={11} />}
      {(INTERVIEW_TYPE_MAP[type] || INTERVIEW_TYPE_MAP.online).label}
    </span>
  )

  const totalCount = tab === 'normal' ? interviews.length : conflicted.length
  const filteredCount = tab === 'normal' ? filteredNormal.length : filteredConflicted.length

  return (
    <div className="animate-slide-in">
      {/* Stats */}
      <div className="grid grid-cols-5 gap-3 mb-5">
        {[
          { label: '面试总数', value: interviews.length, accent: 'text-blue-600' },
          { label: '待面试', value: upcoming, accent: 'text-violet-600' },
          { label: '线上面试', value: onlineCount, accent: 'text-sky-600' },
          { label: '线下面试', value: offlineCount, accent: 'text-emerald-600' },
          { label: '冲突邀约', value: conflicted.length, accent: 'text-amber-600' },
        ].map((item) => (
          <div key={item.label} className="rounded-xl bg-white border border-slate-200 p-4">
            <div className={cn('text-2xl font-semibold', item.accent)}>{item.value}</div>
            <div className="text-xs text-slate-400 mt-1">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Tab 切换：正式排期 / 冲突邀约（默认正式排期） */}
      <div className="inline-flex rounded-xl bg-white border border-slate-200 p-1 mb-4 shadow-sm">
        <button
          onClick={() => setTab('normal')}
          className={cn(
            'inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer',
            tab === 'normal' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'
          )}
        >
          正式排期
          <span className={cn('text-xs px-1.5 py-0.5 rounded', tab === 'normal' ? 'bg-white/20' : 'bg-slate-100 text-slate-400')}>
            {interviews.length}
          </span>
        </button>
        <button
          onClick={() => setTab('conflict')}
          className={cn(
            'inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer',
            tab === 'conflict' ? 'bg-amber-500 text-white' : 'text-slate-500 hover:text-amber-700'
          )}
        >
          <AlertTriangle size={14} />
          冲突邀约
          <span className={cn('text-xs px-1.5 py-0.5 rounded', tab === 'conflict' ? 'bg-white/25' : 'bg-amber-50 text-amber-600')}>
            {conflicted.length}
          </span>
        </button>
      </div>

      {/* Filter bar（两个 Tab 完全一致；冲突邀约没有状态字段，状态下拉禁用） */}
      <div className="bg-white rounded-xl border border-slate-200 p-3 mb-4 flex items-center gap-2 flex-wrap">
        <input
          value={filter.keyword}
          onChange={(e) => setF({ keyword: e.target.value })}
          placeholder={tab === 'normal' ? '搜索岗位 / 公司' : '搜索岗位 / 公司 / HR / 消息内容'}
          className={inputCls + ' flex-1 min-w-[200px]'}
        />
        <select value={filter.type} onChange={(e) => setF({ type: e.target.value })} className={inputCls + ' cursor-pointer'}>
          <option value="all">全部方式</option>
          <option value="online">线上</option>
          <option value="offline">线下</option>
        </select>
        <select
          value={filter.status}
          onChange={(e) => setF({ status: e.target.value })}
          disabled={tab === 'conflict'}
          title={tab === 'conflict' ? '冲突邀约没有状态字段' : undefined}
          className={inputCls + ' cursor-pointer' + (tab === 'conflict' ? ' opacity-40' : '')}
        >
          <option value="all">全部状态</option>
          <option value="pending">待确认</option>
          <option value="confirmed">已确认</option>
          <option value="done">已完成</option>
          <option value="cancelled">已取消</option>
        </select>
        <div className="flex items-center gap-1.5">
          <input type="date" value={filter.dateFrom} onChange={(e) => setF({ dateFrom: e.target.value })} className={inputCls + ' cursor-pointer'} title="开始日期" />
          <span className="text-slate-400 text-sm">~</span>
          <input type="date" value={filter.dateTo} onChange={(e) => setF({ dateTo: e.target.value })} className={inputCls + ' cursor-pointer'} title="结束日期" />
        </div>
        {hasFilter && (
          <button
            onClick={() => setFilter(EMPTY_FILTER)}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm text-slate-500 hover:bg-slate-50 hover:text-slate-700 transition-colors cursor-pointer"
            title="清空筛选条件"
          >
            <RotateCcw size={13} /> 重置
          </button>
        )}
      </div>

      {/* Table card */}
      <div className={cn(
        'bg-white rounded-xl border overflow-hidden shadow-sm',
        tab === 'conflict' ? 'border-amber-200' : 'border-slate-200'
      )}>
        <div className={cn(
          'flex items-center justify-between p-4 flex-wrap gap-3 border-b',
          tab === 'conflict' ? 'border-amber-100 bg-amber-50/60' : 'border-slate-100 bg-slate-50/50'
        )}>
          <div className={cn('text-sm font-medium flex items-center gap-2', tab === 'conflict' ? 'text-amber-800' : 'text-slate-700')}>
            {tab === 'conflict' && <AlertTriangle size={15} className="text-amber-500" />}
            {tab === 'normal' ? '正式排期' : '冲突邀约留档'}
            <span className="text-xs font-normal opacity-70">
              {hasFilter ? `筛选出 ${filteredCount} / ${totalCount}` : `共 ${totalCount}`}
              {tab === 'conflict' && ' （与已排期时间冲突，未正式入排期，仅供跟进参考）'}
            </span>
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
          {tab === 'normal' ? (
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
                {!loading && filteredNormal.length > 0 && filteredNormal.map((it) => (
                  <tr key={it.id} className="border-t border-slate-100 hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4">{renderJobCell(it.job_title, it.job_url)}</td>
                    <td className="py-3 px-4 text-slate-600">{it.company}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5 text-slate-700">
                        <CalendarDays size={13} className="text-slate-400 flex-shrink-0" />
                        <span>{formatTime(it.interview_date, it.start_time, it.end_time)}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4">{renderTypeBadge(it.interview_type)}</td>
                    <td className="py-3 px-4 text-slate-600">
                      {it.interview_type === 'offline' ? (it.location || '-') : '视频 / 电话'}
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
                {!loading && filteredNormal.length === 0 && (
                  <tr><td colSpan={6} className="py-10 text-center text-slate-400">
                    {hasFilter ? '没有符合筛选条件的面试' : '暂无面试安排'}
                  </td></tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-amber-100 bg-amber-50/40">
                  <th className="text-left py-2.5 px-4 text-xs font-medium text-amber-700/80">面试岗位</th>
                  <th className="text-left py-2.5 px-4 text-xs font-medium text-amber-700/80">公司</th>
                  <th className="text-left py-2.5 px-4 text-xs font-medium text-amber-700/80">HR</th>
                  <th className="text-left py-2.5 px-4 text-xs font-medium text-amber-700/80">邀约时间</th>
                  <th className="text-left py-2.5 px-4 text-xs font-medium text-amber-700/80">冲突原因</th>
                  <th className="text-left py-2.5 px-4 text-xs font-medium text-amber-700/80">HR 消息原文</th>
                </tr>
              </thead>
              <tbody>
                {!loading && filteredConflicted.map((c) => (
                  <tr key={c.id} className="border-t border-amber-50 hover:bg-amber-50/40 transition-colors align-top">
                    <td className="py-3 px-4">{renderJobCell(c.job_title, c.job_url)}</td>
                    <td className="py-3 px-4 text-slate-600">{c.company}</td>
                    <td className="py-3 px-4 text-slate-600">{c.hr_name || '-'}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5 text-slate-700">
                        <CalendarDays size={13} className="text-slate-400 flex-shrink-0" />
                        <span>{formatTime(c.interview_date, c.start_time, c.end_time)}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 max-w-[240px]">
                      <span className="text-amber-700 text-xs leading-5">{c.conflict_reason}</span>
                    </td>
                    <td className="py-3 px-4 max-w-[320px]">
                      <span className="text-slate-500 text-xs leading-5 line-clamp-2 whitespace-pre-wrap" title={c.hr_message || ''}>
                        {(c.hr_message || c.notes || '-').slice(0, 120)}
                      </span>
                    </td>
                  </tr>
                ))}
                {loading && (
                  <tr><td colSpan={6} className="py-10 text-center"><Spinner size="md" /></td></tr>
                )}
                {!loading && filteredConflicted.length === 0 && (
                  <tr><td colSpan={6} className="py-10 text-center text-slate-400">
                    {hasFilter ? '没有符合筛选条件的冲突邀约' : '暂无冲突邀约'}
                  </td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
