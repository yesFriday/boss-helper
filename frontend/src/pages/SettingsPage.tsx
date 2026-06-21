import { useState, useEffect } from 'react'
import { Save, RefreshCw, Heart, Plus, Trash2 } from 'lucide-react'
import { useSettingsStore } from '../stores/settingsStore'
import { useSystemStore } from '../stores/systemStore'
import { useNotificationStore } from '../stores/notificationStore'
import { settingsApi } from '../api/settings'
import { systemApi } from '../api/system'
import { AI_PLATFORMS } from '../lib/constants'

interface TimeSlot {
  label: string
  start: string
  end: string
}

export function SettingsPage() {
  const { aiKeyConfigured } = useSettingsStore()
  const { sessionStatus } = useSystemStore()
  const { addToast } = useNotificationStore()
  const [timeSlots, setTimeSlots] = useState<TimeSlot[]>([])
  const [formData, setFormData] = useState({
    greeting_template: '',
    ai_reply_style: 'professional',
    daily_apply_limit: '15',
    min_reply_delay_sec: '30',
    max_reply_delay_sec: '120',
    batch_delay_min_sec: '30',
    batch_delay_max_sec: '90',
    resume_summary: '',
    wechat_id: '',
    search_keywords: '',
    auto_reply_enabled: 'true',
    ai_platform: '',
    ai_api_key: '',
    ai_base_url: '',
    ai_model: '',
    interview_format: 'both',
    interview_time_slots: '',
    interview_daily_limit: '3',
  })

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      const res = await settingsApi.getSettings()
      const s = res.settings || {}
      
      // Parse time slots
      let parsedSlots: TimeSlot[] = []
      try {
        if (s.interview_time_slots) {
          const parsed = JSON.parse(s.interview_time_slots)
          if (Array.isArray(parsed)) {
            parsedSlots = parsed.map((item: any) => ({
              label: item.label || '',
              start: item.start || '',
              end: item.end || '',
            }))
          } else {
            throw new Error()
          }
        } else {
          throw new Error()
        }
      } catch {
        parsedSlots = [
          { label: '上午', start: '09:00', end: '12:00' },
          { label: '下午', start: '14:00', end: '18:00' },
        ]
      }
      setTimeSlots(parsedSlots)

      setFormData({
        greeting_template: s.greeting_template || '',
        ai_reply_style: s.ai_reply_style || 'professional',
        daily_apply_limit: s.daily_apply_limit || '15',
        min_reply_delay_sec: s.min_reply_delay_sec || '30',
        max_reply_delay_sec: s.max_reply_delay_sec || '120',
        batch_delay_min_sec: s.batch_delay_min_sec || '30',
        batch_delay_max_sec: s.batch_delay_max_sec || '90',
        resume_summary: s.resume_summary || '',
        wechat_id: s.wechat_id || '',
        search_keywords: (s.search_keywords || '').replace(/,/g, '\n'),
        auto_reply_enabled: s.auto_reply_enabled || 'true',
        ai_platform: '',
        ai_api_key: '',
        ai_base_url: s.ai_base_url || '',
        ai_model: s.ai_model || '',
        interview_format: s.interview_format || 'both',
        interview_time_slots: s.interview_time_slots || '',
        interview_daily_limit: s.interview_daily_limit || '3',
      })
      useSettingsStore.getState().setAiKeyConfigured(s.ai_key_configured === 'true')
    } catch {}
  }

  const handleSave = async () => {
    try {
      await settingsApi.updateSettings({
        greeting_template: formData.greeting_template,
        ai_reply_style: formData.ai_reply_style,
        daily_apply_limit: formData.daily_apply_limit,
        min_reply_delay_sec: formData.min_reply_delay_sec,
        max_reply_delay_sec: formData.max_reply_delay_sec,
        batch_delay_min_sec: formData.batch_delay_min_sec,
        batch_delay_max_sec: formData.batch_delay_max_sec,
        resume_summary: formData.resume_summary,
        wechat_id: formData.wechat_id,
        search_keywords: formData.search_keywords.replace(/\n/g, ','),
        auto_reply_enabled: formData.auto_reply_enabled,
        ai_base_url: formData.ai_base_url,
        ai_model: formData.ai_model,
        interview_format: formData.interview_format,
        interview_time_slots: JSON.stringify(timeSlots),
        interview_daily_limit: formData.interview_daily_limit,
        ...(formData.ai_api_key ? { ai_api_key: formData.ai_api_key } : {}),
      })
      addToast('设置已保存', 'success')
      if (formData.ai_api_key) {
        useSettingsStore.getState().setAiKeyConfigured(true)
        setFormData((prev) => ({ ...prev, ai_api_key: '' }))
      }
    } catch {
      addToast('保存失败', 'error')
    }
  }

  const handleRelogin = async () => {
    if (!confirm('浏览器将打开BOSS登录页，确定继续？')) return
    useSystemStore.getState().setSessionStatus('checking')
    try {
      const res = await systemApi.relogin()
      useSystemStore.getState().setSessionStatus(res.status === 'ok' ? 'ok' : 'expired')
      addToast(res.status === 'ok' ? '登录成功' : res.message || '失败', res.status === 'ok' ? 'success' : 'error')
    } catch {
      useSystemStore.getState().setSessionStatus('')
      addToast('操作失败', 'error')
    }
  }

  const handleHeartbeat = async () => {
    useSystemStore.getState().setSessionStatus('checking')
    try {
      const res = await systemApi.heartbeat()
      useSystemStore.getState().setSessionStatus(res.alive ? 'ok' : 'expired')
    } catch {
      useSystemStore.getState().setSessionStatus('')
    }
  }

  const handlePlatformChange = (platform: string) => {
    const cfg = AI_PLATFORMS[platform]
    if (!cfg) return
    setFormData((prev) => ({
      ...prev,
      ai_platform: platform,
      ai_base_url: cfg.baseUrl,
      ai_model: cfg.models[0]?.v || '',
    }))
  }

  return (
    <div className="animate-slide-in space-y-5">
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">招呼语设置</h3>
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">招呼语模板</label>
            <textarea
              value={formData.greeting_template}
              onChange={(e) => setFormData((prev) => ({ ...prev, greeting_template: e.target.value }))}
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all min-h-[60px] resize-y"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">AI回复风格</label>
            <select
              value={formData.ai_reply_style}
              onChange={(e) => setFormData((prev) => ({ ...prev, ai_reply_style: e.target.value }))}
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer"
            >
              <option value="professional">专业</option>
              <option value="casual">轻松</option>
              <option value="enthusiastic">热情</option>
            </select>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">频率限制</h3>
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">每日投递上限</label>
            <input
              type="number"
              value={formData.daily_apply_limit}
              onChange={(e) => setFormData((prev) => ({ ...prev, daily_apply_limit: e.target.value }))}
              min={1}
              max={30}
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">回复间隔(秒)</label>
            <div className="flex-1 flex items-center gap-3">
              <input
                type="number"
                value={formData.min_reply_delay_sec}
                onChange={(e) => setFormData((prev) => ({ ...prev, min_reply_delay_sec: e.target.value }))}
                min={10}
                max={300}
                className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
              <span className="text-slate-400 font-semibold">—</span>
              <input
                type="number"
                value={formData.max_reply_delay_sec}
                onChange={(e) => setFormData((prev) => ({ ...prev, max_reply_delay_sec: e.target.value }))}
                min={20}
                max={600}
                className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">投递间隔(秒)</label>
            <div className="flex-1 flex items-center gap-3">
              <input
                type="number"
                value={formData.batch_delay_min_sec}
                onChange={(e) => setFormData((prev) => ({ ...prev, batch_delay_min_sec: e.target.value }))}
                min={5}
                max={300}
                className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
              <span className="text-slate-400 font-semibold">—</span>
              <input
                type="number"
                value={formData.batch_delay_max_sec}
                onChange={(e) => setFormData((prev) => ({ ...prev, batch_delay_max_sec: e.target.value }))}
                min={10}
                max={600}
                className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">个人资料</h3>
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">微信号</label>
            <input
              type="text"
              value={formData.wechat_id}
              onChange={(e) => setFormData((prev) => ({ ...prev, wechat_id: e.target.value }))}
              placeholder="AI会引导HR添加"
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">简历摘要</label>
            <textarea
              value={formData.resume_summary}
              onChange={(e) => setFormData((prev) => ({ ...prev, resume_summary: e.target.value }))}
              placeholder="技能、项目经验..."
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all min-h-[60px] resize-y"
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">面试自动排程设置</h3>
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">接受面试形式</label>
            <select
              value={formData.interview_format}
              onChange={(e) => setFormData((prev) => ({ ...prev, interview_format: e.target.value }))}
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer"
            >
              <option value="both">线上线下均可</option>
              <option value="online">仅接受线上面试</option>
              <option value="offline">仅接受线下面试</option>
            </select>
          </div>
          <div className="flex items-start gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0 pt-2">面试期望时段</label>
            <div className="flex-1 space-y-3">
              {timeSlots.map((slot, index) => (
                <div key={index} className="flex items-center gap-3">
                  <input
                    type="text"
                    value={slot.label}
                    placeholder="时段名称 (如: 上午)"
                    onChange={(e) => {
                      const newSlots = [...timeSlots]
                      newSlots[index].label = e.target.value
                      setTimeSlots(newSlots)
                    }}
                    className="w-40 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
                  />
                  <input
                    type="time"
                    value={slot.start}
                    onChange={(e) => {
                      const newSlots = [...timeSlots]
                      newSlots[index].start = e.target.value
                      setTimeSlots(newSlots)
                    }}
                    className="w-32 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all cursor-pointer"
                  />
                  <span className="text-slate-400 font-semibold">—</span>
                  <input
                    type="time"
                    value={slot.end}
                    onChange={(e) => {
                      const newSlots = [...timeSlots]
                      newSlots[index].end = e.target.value
                      setTimeSlots(newSlots)
                    }}
                    className="w-32 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all cursor-pointer"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setTimeSlots(timeSlots.filter((_, i) => i !== index))
                    }}
                    className="p-2.5 rounded-lg text-rose-500 hover:bg-rose-50 transition-colors cursor-pointer"
                    title="删除此时间段"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() => {
                  setTimeSlots([...timeSlots, { label: '', start: '09:00', end: '18:00' }])
                }}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition-colors cursor-pointer mt-1"
              >
                <Plus size={16} />
                添加时间段
              </button>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">每日面试上限</label>
            <input
              type="number"
              value={formData.interview_daily_limit}
              onChange={(e) => setFormData((prev) => ({ ...prev, interview_daily_limit: e.target.value }))}
              min={1}
              max={10}
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">搜索关键词</h3>
        <div className="flex items-start gap-3">
          <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0 pt-2">关键词</label>
          <textarea
            value={formData.search_keywords}
            onChange={(e) => setFormData((prev) => ({ ...prev, search_keywords: e.target.value }))}
            placeholder="AI Agent&#10;大模型开发&#10;AI产品经理&#10;RAG开发"
            rows={5}
            className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all min-h-[80px] resize-y"
          />
        </div>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">AI模型配置</h3>
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">平台</label>
            <select
              value={formData.ai_platform}
              onChange={(e) => handlePlatformChange(e.target.value)}
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer"
            >
              <option value="">-- 选择平台 --</option>
              <option value="deepseek">DeepSeek</option>
              <option value="openrouter">OpenRouter</option>
              <option value="mimo">小米MiMo</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">API Key</label>
            <div className="flex-1 flex items-center gap-2">
              <input
                type="password"
                value={formData.ai_api_key}
                onChange={(e) => setFormData((prev) => ({ ...prev, ai_api_key: e.target.value }))}
                placeholder="输入API Key"
                className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
              <span className="text-xs">
                {aiKeyConfigured ? (
                  <span className="text-emerald-500 font-semibold">已配置</span>
                ) : (
                  <span className="text-amber-500 font-semibold">未配置</span>
                )}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">Base URL</label>
            <input
              type="text"
              value={formData.ai_base_url}
              onChange={(e) => setFormData((prev) => ({ ...prev, ai_base_url: e.target.value }))}
              placeholder="自动填充"
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">模型</label>
            <input
              type="text"
              value={formData.ai_model}
              onChange={(e) => setFormData((prev) => ({ ...prev, ai_model: e.target.value }))}
              placeholder="选择或输入模型名"
              list="modelList"
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
            />
            <datalist id="modelList">
              {formData.ai_platform && AI_PLATFORMS[formData.ai_platform]?.models.map((m) => (
                <option key={m.v} value={m.v}>{m.t}</option>
              ))}
            </datalist>
          </div>
          <div className="flex items-center gap-3">
            <label className="w-32 text-sm font-semibold text-slate-600 flex-shrink-0">自动回复</label>
            <select
              value={formData.auto_reply_enabled}
              onChange={(e) => setFormData((prev) => ({ ...prev, auto_reply_enabled: e.target.value }))}
              className="flex-1 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer"
            >
              <option value="true">开启</option>
              <option value="false">关闭</option>
            </select>
          </div>
          <div className="text-xs text-slate-400 pl-32">选择平台后自动填充 Base URL 和可选模型列表</div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4">系统控制</h3>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={handleSave}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-500 shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
          >
            <Save size={16} />
            保存设置
          </button>
          <button
            onClick={handleRelogin}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
          >
            <RefreshCw size={14} />
            重新扫码登录
          </button>
          <button
            onClick={handleHeartbeat}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
          >
            <Heart size={14} />
            心跳保活
          </button>
          {sessionStatus && (
            <span className="text-xs text-slate-400 ml-2">
              {sessionStatus === 'ok' ? '登录态正常' : sessionStatus === 'expired' ? '已过期' : sessionStatus === 'checking' ? '检测中...' : ''}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}