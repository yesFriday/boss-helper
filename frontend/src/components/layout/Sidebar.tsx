import { useState } from 'react'
import { Search, ClipboardList, MessageSquare, Smartphone, Settings, PanelLeftClose, PanelLeftOpen, Play, Square, Bot, Zap } from 'lucide-react'
import { useAppStore, type TabType } from '../../stores/appStore'
import { useSystemStore } from '../../stores/systemStore'
import { useSchedulerStore } from '../../stores/schedulerStore'
import { useNotificationStore } from '../../stores/notificationStore'
import { systemApi } from '../../api/system'
import { cn } from '../../lib/cn'

interface NavGroup {
  label?: string
  items: { tab: TabType; icon: React.ReactNode; label: string; badge?: number }[]
}

const PHASE_LABEL: Record<string, string> = {
  idle: '待命中',
  searching: '搜索中',
  applying: '投递中',
  paused: '时间外',
  chatting: '回复HR中',
}

const navGroups: NavGroup[] = [
  {
    items: [
      { tab: 'chat', icon: <MessageSquare size={17} />, label: '消息' },
      { tab: 'search', icon: <Search size={17} />, label: '岗位搜索' },
    ],
  },
  {
    label: '记录',
    items: [
      { tab: 'applications', icon: <ClipboardList size={17} />, label: '投递记录' },
      { tab: 'wechat', icon: <Smartphone size={17} />, label: '微信记录' },
    ],
  },
  {
    label: '控制',
    items: [
      { tab: 'automation', icon: <Bot size={17} />, label: 'AI 调度' },
      { tab: 'settings', icon: <Settings size={17} />, label: '设置' },
    ],
  },
]

export function Sidebar() {
  const { activeTab, setActiveTab, sidebarCollapsed, toggleSidebar } = useAppStore()
  const { browserRunning, monitorRunning, monitorPaused, toggleMonitor } = useSystemStore()
  const { status: schedulerStatus } = useSchedulerStore()
  const { addToast } = useNotificationStore()
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)

  const handleStart = async () => {
    setStarting(true)
    try {
      const res = await systemApi.startSystem()
      if (res.status === 'started') {
        const status = await systemApi.getStatus()
        useSystemStore.getState().updateFromStatus(status)
        addToast('浏览器已启动', 'success')
      } else {
        addToast(res.message || '启动失败', 'error')
      }
    } catch {
      addToast('启动失败', 'error')
    } finally {
      setStarting(false)
    }
  }

  const handleStop = async () => {
    setStopping(true)
    try {
      await systemApi.stopSystem()
      const status = await systemApi.getStatus()
      useSystemStore.getState().updateFromStatus(status)
      addToast('系统已停止', 'info')
    } catch {
      addToast('停止失败', 'error')
    } finally {
      setStopping(false)
    }
  }

  const schedulerActive = schedulerStatus.active
  const phaseLabel = PHASE_LABEL[schedulerStatus.phase] || '待命中'
  const todayCount = schedulerStatus.today_count

  return (
    <aside className={cn(
      'flex-shrink-0 bg-white border-r border-slate-200 flex flex-col z-10 transition-all duration-200 select-none',
      sidebarCollapsed ? 'w-14' : 'w-52'
    )}>
      {/* Logo */}
      <div className={cn('px-3 py-4 flex items-center', sidebarCollapsed ? 'justify-center' : 'gap-2.5')}>
        {sidebarCollapsed ? (
          <span className="h-7 w-7 rounded-lg bg-blue-600 text-white text-sm font-semibold flex items-center justify-center">B</span>
        ) : (
          <>
            <span className="h-7 w-7 rounded-lg bg-blue-600 text-white text-sm font-semibold flex items-center justify-center flex-shrink-0">B</span>
            <div className="min-w-0">
              <h1 className="text-sm font-semibold text-slate-900 leading-tight truncate">BOSS 助手</h1>
              <div className="text-[11px] text-slate-400 leading-tight">AI 自动化求职</div>
            </div>
          </>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-1">
        {navGroups.map((group, gi) => (
          <div key={gi} className={gi > 0 ? 'mt-4' : ''}>
            {group.label && !sidebarCollapsed && (
              <div className="px-3 py-1.5 text-[10px] font-medium text-slate-400 uppercase tracking-wider">
                {group.label}
              </div>
            )}
            {group.label && sidebarCollapsed && (
              <div className="mx-3 my-1 h-px bg-slate-100" />
            )}
            <div className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <button
                  key={item.tab}
                  onClick={() => setActiveTab(item.tab)}
                  title={sidebarCollapsed ? item.label : undefined}
                  className={cn(
                    'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors duration-100 cursor-pointer relative',
                    sidebarCollapsed && 'justify-center px-0 w-10 mx-auto',
                    activeTab === item.tab
                      ? 'bg-blue-50 text-blue-700 font-medium'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  )}
                >
                  <span className={cn('flex-shrink-0', activeTab === item.tab ? 'text-blue-600' : 'text-slate-400')}>{item.icon}</span>
                  {!sidebarCollapsed && (
                    <>
                      <span className="truncate">{item.label}</span>
                      {item.badge ? (
                        <span className="ml-auto bg-red-500 text-white text-[10px] font-medium rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
                          {item.badge}
                        </span>
                      ) : null}
                    </>
                  )}
                </button>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Bottom: Browser control + Status */}
      <div className="px-2 py-3 border-t border-slate-100 space-y-2">
        {/* Browser start/stop */}
        {!sidebarCollapsed ? (
          browserRunning ? (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Square size={12} />
              {stopping ? '停止中...' : '停止浏览器'}
            </button>
          ) : (
            <button
              onClick={handleStart}
              disabled={starting}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Play size={12} />
              {starting ? '启动中...' : '启动浏览器'}
            </button>
          )
        ) : (
          <div className="flex justify-center">
            {browserRunning ? (
              <button
                onClick={handleStop}
                disabled={stopping}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
                title="停止浏览器"
              >
                <Square size={14} />
              </button>
            ) : (
              <button
                onClick={handleStart}
                disabled={starting}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-blue-600 hover:bg-blue-50 transition-colors cursor-pointer"
                title="启动浏览器"
              >
                <Play size={14} />
              </button>
            )}
          </div>
        )}

        {/* Status indicators */}
        {!sidebarCollapsed ? (
          <div className="space-y-1.5 px-1">
            {/* Scheduler status */}
            {schedulerActive && (
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 text-slate-500">
                  <Zap size={11} className="text-blue-500" />
                  <span>{phaseLabel}</span>
                </div>
                <span className="text-blue-600 font-medium">{todayCount}投递</span>
              </div>
            )}
            {/* Monitor status */}
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5 text-slate-500">
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full flex-shrink-0',
                  monitorRunning
                    ? monitorPaused ? 'bg-amber-400' : 'bg-emerald-500'
                    : 'bg-slate-300'
                )} />
                <span>{monitorRunning ? (monitorPaused ? '监控已暂停' : '监控运行中') : '监控未启动'}</span>
              </div>
              {monitorRunning && (
                <button
                  onClick={toggleMonitor}
                  className={cn(
                    'text-[11px] font-medium px-1.5 py-0.5 rounded transition-colors cursor-pointer',
                    monitorPaused ? 'text-emerald-600 hover:bg-emerald-50' : 'text-amber-600 hover:bg-amber-50'
                  )}
                >
                  {monitorPaused ? '恢复' : '暂停'}
                </button>
              )}
            </div>
            {/* Browser status */}
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', browserRunning ? 'bg-emerald-500' : 'bg-slate-300')} />
              <span>浏览器 {browserRunning ? '运行中' : '未启动'}</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1.5">
            <span className={cn('w-1.5 h-1.5 rounded-full', browserRunning ? 'bg-emerald-500' : 'bg-slate-300')} title={`浏览器${browserRunning ? '运行中' : '未启动'}`} />
            <span className={cn('w-1.5 h-1.5 rounded-full',
              monitorRunning ? (monitorPaused ? 'bg-amber-400' : 'bg-emerald-500') : 'bg-slate-300'
            )} title={`监控${monitorRunning ? (monitorPaused ? '已暂停' : '运行中') : '未启动'}`} />
          </div>
        )}
      </div>

      {/* Collapse toggle */}
      <div className="px-2 pb-2">
        <button
          onClick={toggleSidebar}
          className={cn(
            'flex items-center py-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-50 transition-colors cursor-pointer',
            sidebarCollapsed ? 'justify-center w-full' : 'justify-center w-full'
          )}
          title={sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
        >
          {sidebarCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </button>
      </div>
    </aside>
  )
}
