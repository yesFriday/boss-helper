import { useState, useEffect } from 'react'
import {
  Save, RefreshCw, Heart, Plus, Trash2, Eye, EyeOff, MessageSquare, Gauge,
  User, CalendarClock, Search, Bot, ChevronDown, Zap
} from 'lucide-react'
import { useSettingsStore } from '../stores/settingsStore'
import { useSystemStore } from '../stores/systemStore'
import { useNotificationStore } from '../stores/notificationStore'
import { settingsApi } from '../api/settings'
import { systemApi } from '../api/system'
import { AI_PLATFORMS } from '../lib/constants'
import { Button } from '../components/common/Button'
import { cn } from '../lib/cn'

interface TimeSlot {
  label: string
  start: string
  end: string
}

function Section({
  icon,
  title,
  description,
  defaultOpen = true,
  children,
}: {
  icon: React.ReactNode
  title: string
  description?: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="rounded-xl bg-white border border-slate-200 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-slate-50/50 transition-colors cursor-pointer"
      >
        <span className="text-slate-400 flex-shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {description && <p className="text-xs text-slate-400 mt-0.5">{description}</p>}
        </div>
        <ChevronDown size={16} className={cn('text-slate-400 flex-shrink-0 transition-transform duration-200', open && 'rotate-180')} />
      </button>
      {open && <div className="px-5 pb-5 space-y-4 border-t border-slate-100 pt-4">{children}</div>}
    </section>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700">{label}</label>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
      <div className="mt-2">{children}</div>
    </div>
  )
}

const inputCls = "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition-colors placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15"

export function SettingsPage() {
  const { aiKeyConfigured } = useSettingsStore()
  const { sessionStatus } = useSystemStore()
  const { addToast } = useNotificationStore()
  const [timeSlots, setTimeSlots] = useState<TimeSlot[]>([])
  const [showApiKey, setShowApiKey] = useState(false)
  const [testingAi, setTestingAi] = useState(false)
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
    ai_is_full_url: 'false',
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
      let parsedSlots: TimeSlot[] = []
      try {
        if (s.interview_time_slots) {
          const parsed = JSON.parse(s.interview_time_slots)
          if (Array.isArray(parsed)) {
            parsedSlots = parsed.map((item: any) => ({ label: item.label || '', start: item.start || '', end: item.end || '' }))
          } else { throw new Error() }
        } else { throw new Error() }
      } catch {
        parsedSlots = [
          { label: '上午', start: '09:00', end: '12:00' },
          { label: '下午', start: '14:00', end: '18:00' },
        ]
      }
      setTimeSlots(parsedSlots)

      let detectedPlatform = ''
      if (s.ai_base_url) {
        const found = Object.entries(AI_PLATFORMS).find(([_, cfg]) => cfg.baseUrl === s.ai_base_url)
        detectedPlatform = found ? found[0] : 'custom'
      }

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
        ai_platform: detectedPlatform,
        ai_api_key: s.ai_api_key || '',
        ai_base_url: s.ai_base_url || '',
        ai_model: s.ai_model || '',
        ai_is_full_url: s.ai_is_full_url || 'false',
        interview_format: s.interview_format || 'both',
        interview_time_slots: s.interview_time_slots || '',
        interview_daily_limit: s.interview_daily_limit || '3',
      })
      useSettingsStore.getState().setAiKeyConfigured(s.ai_key_configured === 'true')
    } catch {}
  }

  const setField = (key: keyof typeof formData, value: string) =>
    setFormData((prev) => ({ ...prev, [key]: value }))

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
        ai_is_full_url: formData.ai_is_full_url,
        interview_format: formData.interview_format,
        interview_time_slots: JSON.stringify(timeSlots),
        interview_daily_limit: formData.interview_daily_limit,
        ai_api_key: formData.ai_api_key,
      })
      addToast('设置已保存', 'success')
      if (formData.ai_api_key) useSettingsStore.getState().setAiKeyConfigured(true)
    } catch { addToast('保存失败', 'error') }
  }

  const handleTestAi = async () => {
    setTestingAi(true)
    try {
      const res = await settingsApi.testAiSettings({
        ai_api_key: formData.ai_api_key,
        ai_base_url: formData.ai_base_url,
        ai_model: formData.ai_model,
        ai_is_full_url: formData.ai_is_full_url,
      })
      addToast(res.status === 'ok' ? res.message : (res.message || '测试失败'), res.status === 'ok' ? 'success' : 'error')
    } catch (e: any) { addToast(e.message || '网络错误', 'error') }
    finally { setTestingAi(false) }
  }

  const handleRelogin = async () => {
    if (!confirm('浏览器将打开BOSS登录页，确定继续？')) return
    useSystemStore.getState().setSessionStatus('checking')
    try {
      const res = await systemApi.relogin()
      useSystemStore.getState().setSessionStatus(res.status === 'ok' ? 'ok' : 'expired')
      addToast(res.status === 'ok' ? '登录成功' : (res.message || '失败'), res.status === 'ok' ? 'success' : 'error')
    } catch { useSystemStore.getState().setSessionStatus(''); addToast('操作失败', 'error') }
  }

  const handleHeartbeat = async () => {
    useSystemStore.getState().setSessionStatus('checking')
    try {
      const res = await systemApi.heartbeat()
      useSystemStore.getState().setSessionStatus(res.alive ? 'ok' : 'expired')
    } catch { useSystemStore.getState().setSessionStatus('') }
  }

  const handlePlatformChange = (platform: string) => {
    const cfg = AI_PLATFORMS[platform]
    if (!cfg) return
    setFormData((prev) => ({ ...prev, ai_platform: platform, ai_base_url: cfg.baseUrl, ai_model: cfg.models[0]?.v || '' }))
  }

  return (
    <div className="animate-slide-in space-y-3 max-w-3xl">
      {/* Quick status bar */}
      <div className="rounded-xl bg-white border border-slate-200 p-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className={cn(
              'w-2 h-2 rounded-full',
              sessionStatus === 'ok' ? 'bg-emerald-500' : sessionStatus === 'expired' ? 'bg-red-500' : sessionStatus === 'checking' ? 'bg-amber-400 animate-pulse' : 'bg-slate-300'
            )} />
            <span className="text-sm text-slate-600">
              {sessionStatus === 'ok' ? '登录态正常' : sessionStatus === 'expired' ? '登录已过期' : sessionStatus === 'checking' ? '检测中...' : '未知状态'}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Zap size={13} className={aiKeyConfigured ? 'text-emerald-500' : 'text-slate-300'} />
            <span>AI {aiKeyConfigured ? '已配置' : '未配置'}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={handleHeartbeat}><Heart size={13} />心跳</Button>
          <Button variant="danger" size="sm" onClick={handleRelogin}><RefreshCw size={13} />重新登录</Button>
          <Button variant="primary" size="sm" onClick={handleSave}><Save size={13} />保存</Button>
        </div>
      </div>

      {/* 回复设置 - high frequency */}
      <Section icon={<MessageSquare size={16} />} title="回复设置" description="AI 回复风格与自动回复开关">
        <Field label="AI 回复风格" hint="AI 自动回复消息时使用的语气">
          <select value={formData.ai_reply_style} onChange={(e) => setField('ai_reply_style', e.target.value)} className={inputCls + ' cursor-pointer'}>
            <option value="professional">专业正式</option>
            <option value="casual">轻松随和</option>
            <option value="enthusiastic">热情积极</option>
          </select>
        </Field>
        <Field label="自动回复">
          <select value={formData.auto_reply_enabled} onChange={(e) => setField('auto_reply_enabled', e.target.value)} className={inputCls + ' cursor-pointer'}>
            <option value="true">开启</option>
            <option value="false">关闭</option>
          </select>
        </Field>
      </Section>

      {/* 打招呼配置 */}
      <Section icon={<Gauge size={16} />} title="打招呼配置" description="控制每日沟通发起频率，降低风控风险" defaultOpen={false}>
        <Field label="每日打招呼上限" hint="每天最多向 HR 发起沟通(点击立即沟通)的次数">
          <input type="number" value={formData.daily_apply_limit} onChange={(e) => setField('daily_apply_limit', e.target.value)} min={1} max={50} className={inputCls} />
        </Field>
        <Field label="回复间隔(秒)" hint="自动回复两条消息之间的随机延迟">
          <div className="flex items-center gap-2">
            <input type="number" value={formData.min_reply_delay_sec} onChange={(e) => setField('min_reply_delay_sec', e.target.value)} min={10} max={300} className={inputCls + ' flex-1'} />
            <span className="text-slate-400 text-sm">—</span>
            <input type="number" value={formData.max_reply_delay_sec} onChange={(e) => setField('max_reply_delay_sec', e.target.value)} min={20} max={600} className={inputCls + ' flex-1'} />
          </div>
        </Field>
        <Field label="打招呼间隔(秒)" hint="连续向多个岗位发起沟通之间的随机延迟">
          <div className="flex items-center gap-2">
            <input type="number" value={formData.batch_delay_min_sec} onChange={(e) => setField('batch_delay_min_sec', e.target.value)} min={5} max={300} className={inputCls + ' flex-1'} />
            <span className="text-slate-400 text-sm">—</span>
            <input type="number" value={formData.batch_delay_max_sec} onChange={(e) => setField('batch_delay_max_sec', e.target.value)} min={10} max={600} className={inputCls + ' flex-1'} />
          </div>
        </Field>
      </Section>

      {/* 搜索关键词 */}
      <Section icon={<Search size={16} />} title="搜索关键词" description="自动搜索职位时使用，每行一个" defaultOpen={false}>
        <textarea
          value={formData.search_keywords}
          onChange={(e) => setField('search_keywords', e.target.value)}
          placeholder={'AI Agent\n大模型开发\nAI产品经理\nRAG开发'}
          rows={4}
          className={inputCls + ' resize-y min-h-[80px] font-mono text-xs'}
        />
      </Section>

      {/* 招呼语 */}
      <Section icon={<MessageSquare size={16} />} title="招呼语" description="投递后自动发送给 HR 的首条消息" defaultOpen={false}>
        <textarea
          value={formData.greeting_template}
          onChange={(e) => setField('greeting_template', e.target.value)}
          className={inputCls + ' resize-y min-h-[80px]'}
          placeholder="您好,我对这个岗位很感兴趣..."
        />
      </Section>

      {/* 个人资料 */}
      <Section icon={<User size={16} />} title="个人资料" description="提供给 AI 的个人上下文信息" defaultOpen={false}>
        <Field label="微信号" hint="AI 会引导 HR 添加此微信号">
          <input type="text" value={formData.wechat_id} onChange={(e) => setField('wechat_id', e.target.value)} placeholder="your_wechat" className={inputCls} />
        </Field>
        <Field label="简历摘要" hint="技能与项目经验，供 AI 回复时参考">
          <textarea value={formData.resume_summary} onChange={(e) => setField('resume_summary', e.target.value)} placeholder="技能、项目经验..." className={inputCls + ' resize-y min-h-[80px]'} />
        </Field>
      </Section>

      {/* 面试排程 */}
      <Section icon={<CalendarClock size={16} />} title="面试排程" description="AI 与 HR 约定面试时间的规则" defaultOpen={false}>
        <Field label="接受面试形式">
          <select value={formData.interview_format} onChange={(e) => setField('interview_format', e.target.value)} className={inputCls + ' cursor-pointer'}>
            <option value="both">线上线下均可</option>
            <option value="online">仅线上</option>
            <option value="offline">仅线下</option>
          </select>
        </Field>
        <Field label="期望时段" hint="AI 优先选择这些时间段">
          <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {timeSlots.map((slot, index) => (
              <div key={index} className="flex items-center gap-2 p-2.5">
                <input type="text" value={slot.label} placeholder="名称" onChange={(e) => { const n = [...timeSlots]; n[index].label = e.target.value; setTimeSlots(n) }} className="flex-1 min-w-0 rounded-md border border-slate-200 px-2.5 py-1.5 text-sm outline-none focus:border-blue-500" />
                <input type="time" value={slot.start} onChange={(e) => { const n = [...timeSlots]; n[index].start = e.target.value; setTimeSlots(n) }} className="w-24 rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-blue-500 cursor-pointer" />
                <span className="text-slate-300">—</span>
                <input type="time" value={slot.end} onChange={(e) => { const n = [...timeSlots]; n[index].end = e.target.value; setTimeSlots(n) }} className="w-24 rounded-md border border-slate-200 px-2 py-1.5 text-sm outline-none focus:border-blue-500 cursor-pointer" />
                <button type="button" onClick={() => setTimeSlots(timeSlots.filter((_, i) => i !== index))} className="p-1.5 text-red-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors cursor-pointer"><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
          <Button type="button" variant="secondary" size="sm" onClick={() => setTimeSlots([...timeSlots, { label: '', start: '09:00', end: '18:00' }])} className="mt-2">
            <Plus size={13} /> 添加时段
          </Button>
        </Field>
        <Field label="每日面试上限">
          <input type="number" value={formData.interview_daily_limit} onChange={(e) => setField('interview_daily_limit', e.target.value)} min={1} max={10} className={inputCls} />
        </Field>
      </Section>

      {/* AI 模型配置 */}
      <Section icon={<Bot size={16} />} title="AI 模型" description="接入大模型平台以生成智能回复" defaultOpen={false}>
        <Field label="平台">
          <select value={formData.ai_platform} onChange={(e) => handlePlatformChange(e.target.value)} className={inputCls + ' cursor-pointer'}>
            <option value="">-- 选择平台 --</option>
            <option value="deepseek">DeepSeek</option>
            <option value="openrouter">OpenRouter</option>
            <option value="mimo">小米 MiMo</option>
            <option value="custom">自定义</option>
          </select>
        </Field>
        <Field label="API Key">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <input type={showApiKey ? 'text' : 'password'} value={formData.ai_api_key} onChange={(e) => setField('ai_api_key', e.target.value)} placeholder="输入 API Key" className={inputCls + ' pr-10'} />
              <button type="button" onClick={() => setShowApiKey(!showApiKey)} className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 text-slate-400 hover:text-slate-600 rounded cursor-pointer">
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <span className={cn('px-2 py-1 rounded text-xs font-medium flex-shrink-0', aiKeyConfigured ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600')}>
              {aiKeyConfigured ? '已配置' : '未配置'}
            </span>
          </div>
        </Field>
        <Field label="Base URL">
          <input type="text" value={formData.ai_base_url} onChange={(e) => setField('ai_base_url', e.target.value)} placeholder="自动填充或输入 API 地址" className={inputCls} />
          <div className="mt-2 flex items-center">
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={formData.ai_is_full_url === 'true'}
                onChange={(e) => setField('ai_is_full_url', e.target.checked ? 'true' : 'false')}
                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
              />
              <span className="font-medium text-slate-700">完整 URL 模式</span>
              <span className="text-slate-400">（已包含 /chat/completions 等路径，不进行自动拼接）</span>
            </label>
          </div>
        </Field>
        <Field label="模型">
          <input type="text" value={formData.ai_model} onChange={(e) => setField('ai_model', e.target.value)} placeholder="选择或输入模型名" list="modelList" className={inputCls} />
          <datalist id="modelList">
            {formData.ai_platform && AI_PLATFORMS[formData.ai_platform]?.models.map((m) => (
              <option key={m.v} value={m.v}>{m.t}</option>
            ))}
          </datalist>
        </Field>
        <div className="flex items-center gap-3 pt-1">
          <Button type="button" variant="primary" size="sm" onClick={handleTestAi} disabled={testingAi}>
            {testingAi ? '测试中...' : '测试连接'}
          </Button>
          <span className="text-xs text-slate-400">选择平台后自动填充地址和模型</span>
        </div>
      </Section>
    </div>
  )
}
