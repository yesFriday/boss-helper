import { useState, useEffect, useCallback, useRef } from 'react'
import { Play, Square, Trash2, Zap, Search, Clock } from 'lucide-react'
import { cn } from '../lib/cn'
import { TimePicker } from '../components/common/TimePicker'
import { useSchedulerStore } from '../stores/schedulerStore'
import { useNotificationStore } from '../stores/notificationStore'
import { schedulerApi } from '../api/scheduler'
import type { SchedulerConfig } from '../api/scheduler'
import { CITY_GROUPS } from '../lib/constants'

const DAY_LABELS = [
  { value: 1, label: '一' },
  { value: 2, label: '二' },
  { value: 3, label: '三' },
  { value: 4, label: '四' },
  { value: 5, label: '五' },
  { value: 6, label: '六' },
  { value: 7, label: '日' },
]

const HR_ACTIVE_OPTIONS = [
  { value: '在线', label: '在线' },
  { value: '刚刚活跃', label: '刚刚活跃' },
  { value: '今日活跃', label: '今日活跃' },
  { value: '3日内活跃', label: '3日内' },
  { value: '本周活跃', label: '本周' },
  { value: '本月活跃', label: '本月' },
]

const PHASE_MAP: Record<string, { label: string; color: string; bg: string }> = {
  idle: { label: '待命中', color: 'text-slate-500', bg: 'bg-slate-500' },
  searching: { label: '搜索中', color: 'text-blue-500', bg: 'bg-blue-500' },
  applying: { label: '投递中', color: 'text-emerald-500', bg: 'bg-emerald-500' },
  paused: { label: '时间外', color: 'text-amber-500', bg: 'bg-amber-500' },
}

export function AutomationPage() {
  const { config, status, setConfig, setStatus } = useSchedulerStore()
  const { addToast } = useNotificationStore()
  const [saving, setSaving] = useState(false)
  const [localConfig, setLocalConfig] = useState<SchedulerConfig>(config)
  const [hrFilter, setHrFilter] = useState<string[]>([])
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hasChanges = useRef(false)

  useEffect(() => {
    schedulerApi.getConfig().then((res) => {
      setConfig(res.config)
      setLocalConfig(res.config)
      const filterStr = res.config.auto_apply?.hr_active_filter || ''
      setHrFilter(filterStr ? filterStr.split(',').filter(Boolean) : HR_ACTIVE_OPTIONS.map(o => o.value))
    }).catch(() => {})
    schedulerApi.getStatus().then((res) => setStatus(res)).catch(() => {})
  }, [setConfig, setStatus])

  const debouncedSave = useCallback((cfg: SchedulerConfig) => {
    hasChanges.current = true
    setLocalConfig(cfg)
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(async () => {
      if (!hasChanges.current) return
      setSaving(true)
      try {
        await schedulerApi.updateConfig(cfg)
        useSchedulerStore.getState().updateConfig(cfg)
        hasChanges.current = false
      } catch {
        addToast('保存失败', 'error')
      } finally {
        setSaving(false)
      }
    }, 1500)
  }, [addToast])

  const saveNow = useCallback(async () => {
    if (saveTimerRef.current) { clearTimeout(saveTimerRef.current); saveTimerRef.current = null }
    if (!hasChanges.current) return
    setSaving(true)
    try {
      // 把 HR 筛选药丸状态写进 config
      const cfg = { ...localConfig, auto_apply: { ...localConfig.auto_apply, hr_active_filter: hrFilter.join(',') } }
      await schedulerApi.updateConfig(cfg)
      useSchedulerStore.getState().updateConfig(cfg)
      hasChanges.current = false
      addToast('设置已保存', 'success')
    } catch {
      addToast('保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }, [localConfig, hrFilter, addToast])

  const handleToggle = useCallback(async () => {
    const newEnabled = !localConfig.enabled
    const cfg = { ...localConfig, enabled: newEnabled }
    setLocalConfig(cfg)
    setSaving(true)
    try {
      await schedulerApi.updateConfig(cfg)
      useSchedulerStore.getState().updateConfig(cfg)
      addToast(newEnabled ? '已启动' : '已停止', 'success')
    } catch {
      addToast('操作失败', 'error')
    } finally {
      setSaving(false)
    }
  }, [localConfig, addToast])

  const toggleDay = useCallback((day: number) => {
    const days = localConfig.days.includes(day)
      ? localConfig.days.filter((d) => d !== day)
      : [...localConfig.days, day].sort()
    debouncedSave({ ...localConfig, days })
  }, [localConfig, debouncedSave])

  const addTimeRange = useCallback(() => {
    debouncedSave({ ...localConfig, time_ranges: [...localConfig.time_ranges, { start: '09:00', end: '18:00' }] })
  }, [localConfig, debouncedSave])

  const removeTimeRange = useCallback((index: number) => {
    debouncedSave({ ...localConfig, time_ranges: localConfig.time_ranges.filter((_, i) => i !== index) })
  }, [localConfig, debouncedSave])

  const updateTimeRange = useCallback((index: number, field: 'start' | 'end', value: string) => {
    const ranges = [...localConfig.time_ranges]
    ranges[index] = { ...ranges[index], [field]: value }
    debouncedSave({ ...localConfig, time_ranges: ranges })
  }, [localConfig, debouncedSave])

  const toggleHrFilter = useCallback((val: string) => {
    setHrFilter(prev => {
      const next = prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val]
      // 同步触发保存
      const cfg = { ...localConfig, auto_apply: { ...localConfig.auto_apply, hr_active_filter: next.join(',') } }
      setLocalConfig(cfg)
      hasChanges.current = true
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      saveTimerRef.current = setTimeout(async () => {
        if (!hasChanges.current) return
        setSaving(true)
        try {
          await schedulerApi.updateConfig(cfg)
          useSchedulerStore.getState().updateConfig(cfg)
          hasChanges.current = false
        } catch {
          addToast('保存失败', 'error')
        } finally { setSaving(false) }
      }, 1500)
      return next
    })
  }, [localConfig, addToast])

  const allCities = CITY_GROUPS.flatMap((g) => g.cities)
  const phase = PHASE_MAP[status.phase] || PHASE_MAP.idle
  const progress = localConfig.auto_apply.daily_limit > 0 ? Math.min(100, (status.today_count / localConfig.auto_apply.daily_limit) * 100) : 0

  return (
    <div className="animate-slide-in space-y-5">
      {/* ═══ 顶部 Hero ═══ */}
      <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
        <div className="flex items-start justify-between mb-5">
          <div>
            <h2 className="text-xl font-bold text-slate-800">AI 自动求职</h2>
            <p className="text-xs text-slate-400 mt-1.5">配置后可自动搜索、投递、AI 回复</p>
          </div>
          <button
            onClick={handleToggle}
            disabled={saving}
            className={cn(
              'flex items-center gap-2.5 px-10 py-4 rounded-2xl text-base font-bold transition-all cursor-pointer shadow-lg',
              localConfig.enabled
                ? 'bg-gradient-to-r from-red-500 to-rose-500 text-white hover:shadow-red-200 hover:-translate-y-0.5'
                : 'bg-gradient-to-r from-emerald-500 to-teal-500 text-white hover:shadow-emerald-200 hover:-translate-y-0.5',
              saving && 'opacity-60 cursor-not-allowed'
            )}
          >
            <Square size={18} className={localConfig.enabled ? '' : 'hidden'} />
            <Play size={18} className={localConfig.enabled ? 'hidden' : ''} />
            {localConfig.enabled ? '停止' : '启动'}
          </button>
        </div>

        {/* 进度条 */}
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-slate-500 font-medium">今日投递进度</span>
            <span className="font-bold text-slate-700">{status.today_count} / {localConfig.auto_apply.daily_limit}</span>
          </div>
          <div className="h-3.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-700',
                progress >= 100 ? 'bg-amber-400' : 'bg-gradient-to-r from-indigo-500 to-purple-500'
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* 状态行 */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-3">
            {localConfig.enabled ? (
              <span className={cn('flex items-center gap-1.5 font-medium', phase.color)}>
                <span className={cn('w-2 h-2 rounded-full animate-pulse', phase.bg)} />
                {phase.label}
              </span>
            ) : (
              <span className="text-slate-400 text-sm">已停止</span>
            )}
            <span className="text-slate-300">|</span>
            <span className="text-xs text-slate-400">下次检查: 30s</span>
          </div>
          <button
            onClick={saveNow}
            className={cn(
              'text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors cursor-pointer',
              hasChanges.current ? 'bg-indigo-100 text-indigo-600' : 'text-slate-400'
            )}
          >
            {saving ? '保存中...' : '保存设置'}
          </button>
        </div>
      </div>

      {/* ═══ 两栏设置 ═══ */}
      <div className="grid grid-cols-2 gap-5">
        {/* 左侧：搜索设置 */}
        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
          <h3 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
            <Search size={14} />
            搜索设置
          </h3>
          <div className="space-y-3.5">
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1.5">关键词</label>
              <input
                type="text"
                value={localConfig.auto_apply.keyword}
                onChange={(e) => debouncedSave({ ...localConfig, auto_apply: { ...localConfig.auto_apply, keyword: e.target.value } })}
                className="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1.5">城市</label>
                <select
                  value={localConfig.auto_apply.city}
                  onChange={(e) => debouncedSave({ ...localConfig, auto_apply: { ...localConfig.auto_apply, city: e.target.value } })}
                  className="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer"
                >
                  {allCities.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1.5">每日上限</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number" min="1" max="150"
                    value={localConfig.auto_apply.daily_limit}
                    onChange={(e) => debouncedSave({ ...localConfig, auto_apply: { ...localConfig.auto_apply, daily_limit: Number(e.target.value) } })}
                    className="w-20 px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
                  />
                  <span className="text-xs text-slate-400">条/天</span>
                </div>
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1.5">HR 活跃度（仅投递以下状态）</label>
              <div className="flex flex-wrap gap-1.5">
                {HR_ACTIVE_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => toggleHrFilter(opt.value)}
                    className={cn(
                      'px-2.5 py-1 rounded-full text-xs font-medium border transition-all cursor-pointer',
                      hrFilter.includes(opt.value)
                        ? 'bg-indigo-50 border-indigo-300 text-indigo-600'
                        : 'bg-slate-50 border-slate-200 text-slate-400 hover:border-slate-300'
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* 右侧：执行时间 */}
        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col">
          <h3 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
            <Clock size={14} />
            执行时间
          </h3>

          {/* 日期 */}
          <div className="mb-4">
            <label className="block text-xs font-semibold text-slate-500 mb-2">执行日期</label>
            <div className="flex gap-2">
              {DAY_LABELS.map((d) => (
                <button
                  key={d.value}
                  onClick={() => toggleDay(d.value)}
                  className={cn(
                    'w-9 h-9 rounded-full text-sm font-semibold transition-all cursor-pointer',
                    localConfig.days.includes(d.value)
                      ? 'bg-indigo-500 text-white shadow-md'
                      : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                  )}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {/* 时段 */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500">执行时段</span>
              <button
                onClick={addTimeRange}
                className="text-xs text-indigo-500 hover:text-indigo-600 font-medium cursor-pointer"
              >
                + 添加
              </button>
            </div>
            <div className="space-y-2">
              {localConfig.time_ranges.length === 0 ? (
                <div className="text-sm text-slate-400 py-2">暂无时段，点击 + 添加</div>
              ) : (
                localConfig.time_ranges.map((tr, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <TimePicker value={tr.start} onChange={(v) => updateTimeRange(i, 'start', v)} />
                    <span className="text-slate-400 text-sm">~</span>
                    <TimePicker value={tr.end} onChange={(v) => updateTimeRange(i, 'end', v)} />
                    <button
                      onClick={() => removeTimeRange(i)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
           </div>
        </div>
      </div>

      {/* ═══ 执行记录 ═══ */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Zap size={14} />
            执行记录
          </h3>
          <span className="text-xs text-slate-400">最近 20 条</span>
        </div>
        <div className={cn('space-y-1.5', status.execution_log.length > 5 && 'max-h-52 overflow-y-auto')}>
          {status.execution_log.length > 0 ? (
            status.execution_log.slice(0, 20).map((entry, i) => (
              <div key={i} className="flex items-start gap-3 text-xs p-2 rounded-lg bg-slate-50">
                <span className="text-slate-400 font-mono whitespace-nowrap">{entry.time}</span>
                <span className="text-slate-600">{entry.tasks.join(' | ')}</span>
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-400 py-4 text-center">暂无执行记录，启动后自动出现</div>
          )}
        </div>
      </div>
    </div>
  )
}
