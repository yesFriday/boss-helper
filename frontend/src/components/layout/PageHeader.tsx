import { useAppStore } from '../../stores/appStore'

const pageTitles: Record<string, { title: string; subtitle?: string }> = {
  chat: { title: '消息', subtitle: '与 HR 的对话记录' },
  search: { title: '岗位搜索', subtitle: '浏览并筛选 BOSS 直聘职位' },
  applications: { title: '投递记录', subtitle: '所有投递与回复状态' },
  wechat: { title: '微信记录', subtitle: 'HR 微信号收集记录' },
  automation: { title: 'AI 调度', subtitle: '自动搜索、投递与回复配置' },
  settings: { title: '设置', subtitle: '参数配置与系统控制' },
}

export function PageHeader() {
  const { activeTab } = useAppStore()
  const meta = pageTitles[activeTab] || { title: '' }

  return (
    <div className="flex-shrink-0 mb-5">
      <h2 className="text-lg font-semibold text-slate-900 tracking-tight">{meta.title}</h2>
      {meta.subtitle && <p className="text-xs text-slate-400 mt-0.5">{meta.subtitle}</p>}
    </div>
  )
}
