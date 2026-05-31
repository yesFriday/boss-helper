import { useState, useEffect, useCallback } from 'react'
import { Clock, Play, Square, Plus, Trash2, Zap, MessageSquare, Search } from 'lucide-react'
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

const PHASE_MAP: Record<string, { label: string; color: string }> = {
  idle: { label: '待命中', color: 'text-slate-500' },
  searching: { label: '搜索中', color: 'text-blue-500' },
  applying: { label: '投递中', color: 'text-emerald-500' },
  paused: { label: '已暂停', color: 'text-amber-500' },
}

function PhaseIcon({ phase }: { phase: string }) {
  if (phase === 'searching') return <Search size={16} />
  if (phase === 'applying') return <Search size={16} className="text-emerald-500" />
  return <Clock size={16} />
}

export function AutomationPage() {
  const { config, status, setConfig, setStatus } = useSchedulerStore()
  const { addToast } = useNotificationStore()
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    schedulerApi.getConfig().then((res) => setConfig(res.config)).catch(() => {})
    schedulerApi.getStatus().then((res) => setStatus(res)).catch(() => {})
  }, [setConfig, setStatus])

  const updateConfig = useCallback((partial: Partial<SchedulerConfig>) => {
    useSchedulerStore.getState().updateConfig(partial)
  }, [])

  const saveConfig = useCallback(async (cfg: SchedulerConfig) => {
    setSaving(true)
    try {
      await schedulerApi.updateConfig(cfg)
    } catch {
      addToast('保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }, [addToast])

  const handleToggle = useCallback(async () => {
    const newEnabled = !config.enabled
    const newConfig = { ...config, enabled: newEnabled }
    updateConfig({ enabled: newEnabled })
    await saveConfig(newConfig)
    addToast(newEnabled ? '已启动' : '已停止', 'success')
  }, [config, updateConfig, saveConfig, addToast])

  const toggleDay = useCallback((day: number) => {
    const days = config.days.includes(day)
      ? config.days.filter((d) => d !== day)
      : [...config.days, day].sort()
    updateConfig({ days })
    saveConfig({ ...config, days })
  }, [config, updateConfig, saveConfig])

  const addTimeRange = useCallback(() => {
    const ranges = [...config.time_ranges, { start: '09:00', end: '18:00' }]
    updateConfig({ time_ranges: ranges })
    saveConfig({ ...config, time_ranges: ranges })
  }, [config, updateConfig, saveConfig])

  const removeTimeRange = useCallback((index: number) => {
    const ranges = config.time_ranges.filter((_, i) => i !== index)
    updateConfig({ time_ranges: ranges })
    saveConfig({ ...config, time_ranges: ranges })
  }, [config, updateConfig, saveConfig])

  const updateTimeRange = useCallback((index: number, field: 'start' | 'end', value: string) => {
    const ranges = [...config.time_ranges]
    ranges[index] = { ...ranges[index], [field]: value }
    updateConfig({ time_ranges: ranges })
    saveConfig({ ...config, time_ranges: ranges })
  }, [config, updateConfig, saveConfig])

  const updateAutoApply = useCallback((partial: Partial<SchedulerConfig['auto_apply']>) => {
    const auto_apply = { ...config.auto_apply, ...partial }
    updateConfig({ auto_apply })
    saveConfig({ ...config, auto_apply })
  }, [config, updateConfig, saveConfig])

  const updateAutoReply = useCallback((partial: Partial<SchedulerConfig['auto_reply']>) => {
    const auto_reply = { ...config.auto_reply, ...partial }
    updateConfig({ auto_reply })
    saveConfig({ ...config, auto_reply })
  }, [config, updateConfig, saveConfig])

  const allCities = CITY_GROUPS.flatMap((g) => g.cities)
  const phase = PHASE_MAP[status.phase] || PHASE_MAP.idle
  const progress = config.auto_apply.daily_limit > 0 ? Math.min(100, (status.today_count / config.auto_apply.daily_limit) * 100) : 0

  return (
    <div className="animate-slide-in flex flex-col gap-5">
      {/* 启动/停止按钮 + 状态 */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-800">AI 自动求职</h2>
            <p className="text-xs text-slate-400 mt-1">配置参数后点击启动，自动搜索、投递、回复</p>
          </div>
          <button
            onClick={handleToggle}
            disabled={saving}
            className={cn(
              'flex items-center gap-2.5 px-8 py-3.5 rounded-xl text-base font-bold transition-all duration-300 cursor-pointer shadow-lg',
              config.enabled
                ? 'bg-gradient-to-r from-red-500 to-rose-500 text-white hover:shadow-red-200 hover:-translate-y-0.5'
                : 'bg-gradient-to-r from-emerald-500 to-teal-500 text-white hover:shadow-emerald-200 hover:-translate-y-0.5',
              saving && 'opacity-50 cursor-not-allowed'
            )}
          >
            <Square size={18} className={config.enabled ? '' : 'hidden'} />
            <Play size={18} className={config.enabled ? 'hidden' : ''} />
            {config.enabled ? '停止' : '启动'}
          </button>
        </div>

        {/* 进度条 */}
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-slate-500">今日投递进度</span>
            <span className="font-semibold text-slate-700">{status.today_count} / {config.auto_apply.daily_limit}</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500',
                progress >= 100 ? 'bg-amber-400' : 'bg-gradient-to-r from-indigo-500 to-purple-500'
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* 状态指示 */}
        <div className="flex items-center gap-2">
          <span className={cn('flex items-center gap-1.5 text-sm font-medium', phase.color)}>
            <PhaseIcon phase={status.phase} />
            {config.enabled ? phase.label : '已停止'}
          </span>
          {saving && <span className="text-xs text-slate-400">保存中...</span>}
        </div>
      </div>

      {/* 执行日志 */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-3">
          <Zap size={14} className="inline mr-1.5 -mt-0.5" />
          执行记录
        </h3>
        <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
          {status.execution_log.length > 0 ? (
            status.execution_log.map((entry, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className="text-slate-400 font-mono whitespace-nowrap">{entry.time}</span>
                <span className="text-slate-600">{entry.tasks.join(' | ')}</span>
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-400">暂无执行记录</div>
          )}
        </div>
      </div>

      {/* 执行时间 */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">
          <Clock size={14} className="inline mr-1.5 -mt-0.5" />
          执行时间
        </h3>

        <div className="mb-4">
          <div className="text-xs font-semibold text-slate-500 mb-2">执行日期</div>
          <div className="flex gap-2">
            {DAY_LABELS.map((d) => (
              <button
                key={d.value}
                onClick={() => toggleDay(d.value)}
                className={cn(
                  'w-10 h-10 rounded-full text-sm font-semibold transition-all duration-200 cursor-pointer',
                  config.days.includes(d.value)
                    ? 'bg-indigo-500 text-white shadow-md'
                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                )}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <hr className="border-slate-100 my-2" />

        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-slate-500">执行时段</span>
            <button
              onClick={addTimeRange}
              className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-indigo-50 text-indigo-500 hover:bg-indigo-100 transition-colors cursor-pointer"
              title="添加时段"
            >
              <Plus size={13} />
            </button>
          </div>
          <div className="flex flex-col gap-2">
            {config.time_ranges.length === 0 ? (
              <div className="text-sm text-slate-400 py-2">暂无时段，点击上方 + 添加</div>
            ) : (
              config.time_ranges.map((tr, i) => (
                <div key={i} className="flex items-center gap-2">
                  <TimePicker value={tr.start} onChange={(v) => updateTimeRange(i, 'start', v)} />
                  <span className="text-slate-400 text-sm">~</span>
                  <TimePicker value={tr.end} onChange={(v) => updateTimeRange(i, 'end', v)} />
                  <button
                    onClick={() => removeTimeRange(i)}
                    className="p-2 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* 搜索设置 */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">
          <Search size={14} className="inline mr-1.5 -mt-0.5" />
          搜索设置
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label className="w-20 text-xs font-semibold text-slate-500">关键词</label>
            <input
              type="text"
              value={config.auto_apply.keyword}
              onChange={(e) => updateAutoApply({ keyword: e.target.value })}
              onBlur={() => saveConfig(config)}
              className="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="w-20 text-xs font-semibold text-slate-500">城市</label>
            <select
              value={config.auto_apply.city}
              onChange={(e) => { updateAutoApply({ city: e.target.value }); saveConfig({ ...config, auto_apply: { ...config.auto_apply, city: e.target.value } }) }}
              className="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer"
            >
              {allCities.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="w-20 text-xs font-semibold text-slate-500">每日上限</label>
            <input
              type="number"
              min="1"
              max="150"
              value={config.auto_apply.daily_limit}
              onChange={(e) => updateAutoApply({ daily_limit: Number(e.target.value) })}
              onBlur={() => saveConfig(config)}
              className="w-24 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
            />
            <span className="text-xs text-slate-400">条/天</span>
          </div>
        </div>
      </div>

      {/* 自动回复 */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">
          <MessageSquare size={14} className="inline mr-1.5 -mt-0.5" />
          自动回复
        </h3>
        <div className="flex items-center gap-3">
          <label className="w-20 text-xs font-semibold text-slate-500">回复风格</label>
          <select
            value={config.auto_reply.style}
            onChange={(e) => { updateAutoReply({ style: e.target.value }); saveConfig({ ...config, auto_reply: { ...config.auto_reply, style: e.target.value } }) }}
            className="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="professional">专业友好</option>
            <option value="enthusiastic">热情积极</option>
            <option value="concise">简洁直接</option>
          </select>
        </div>
      </div>
    </div>
  )
}
