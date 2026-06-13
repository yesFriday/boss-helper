import { Search, ClipboardList, MessageSquare, Smartphone, Clock, Settings, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useAppStore, type TabType } from '../../stores/appStore'
import { useSystemStore } from '../../stores/systemStore'
import { cn } from '../../lib/cn'

const navItems: { tab: TabType; icon: React.ReactNode; label: string }[] = [
  { tab: 'search', icon: <Search size={18} />, label: '岗位搜索' },
  { tab: 'automation', icon: <Clock size={18} />, label: '交给AI' },
  { tab: 'applications', icon: <ClipboardList size={18} />, label: '投递记录' },
  { tab: 'chat', icon: <MessageSquare size={18} />, label: '聊天' },
  { tab: 'wechat', icon: <Smartphone size={18} />, label: '微信记录' },
  { tab: 'settings', icon: <Settings size={18} />, label: '设置' },
]

export function Sidebar() {
  const { activeTab, setActiveTab, sidebarCollapsed, toggleSidebar } = useAppStore()
  const { browserRunning, monitorRunning, monitorPaused, toggleMonitor } = useSystemStore()

  return (
    <aside className={cn(
      'flex-shrink-0 bg-gradient-to-b from-slate-800 to-slate-900 flex flex-col py-5 shadow-xl z-10 transition-all duration-300',
      sidebarCollapsed ? 'w-16' : 'w-60'
    )}>
      <div className={cn('px-6 mb-7 flex items-center', sidebarCollapsed && 'px-0 justify-center')}>
        {sidebarCollapsed ? (
          <h1 className="text-lg font-bold text-white">B</h1>
        ) : (
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">BOSS 控制台</h1>
            <div className="text-xs text-indigo-300 mt-1.5 font-medium">AI 驱动 · 自动化求职</div>
          </div>
        )}
      </div>

      <nav className="flex-1 flex flex-col gap-1 px-3">
        {navItems.map((item) => (
          <button
            key={item.tab}
            onClick={() => setActiveTab(item.tab)}
            title={sidebarCollapsed ? item.label : undefined}
            className={cn(
              'flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 cursor-pointer',
              sidebarCollapsed && 'justify-center px-0',
              activeTab === item.tab
                ? 'bg-indigo-500/20 text-white'
                : 'text-slate-300 hover:bg-white/10 hover:text-white'
            )}
          >
            <span className="opacity-80 flex-shrink-0">{item.icon}</span>
            {!sidebarCollapsed && <span>{item.label}</span>}
          </button>
        ))}
      </nav>

      {!sidebarCollapsed && (
        <div className="px-5 pt-4 border-t border-white/10 flex flex-col gap-2.5">
          <div className="flex items-center gap-2.5 text-xs text-slate-300">
            <span
              className={cn(
                'w-2 h-2 rounded-full flex-shrink-0',
                browserRunning ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]' : 'bg-slate-500'
              )}
            />
            <span>浏览器 {browserRunning ? '运行中' : '未启动'}</span>
          </div>
          <div className="flex items-center justify-between text-xs text-slate-300">
            <div className="flex items-center gap-2.5">
              <span
                className={cn(
                  'w-2 h-2 rounded-full flex-shrink-0',
                  monitorRunning
                    ? monitorPaused
                      ? 'bg-yellow-400 shadow-[0_0_6px_#f59e0b]'
                      : 'bg-emerald-400 shadow-[0_0_6px_#10b981]'
                    : 'bg-slate-500'
                )}
              />
              <span>监控 {monitorRunning ? (monitorPaused ? '已暂停' : '运行中') : '未启动'}</span>
            </div>
            {monitorRunning && (
              <button
                onClick={toggleMonitor}
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-all duration-200 cursor-pointer',
                  monitorPaused
                    ? 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
                    : 'bg-yellow-500/20 text-yellow-300 hover:bg-yellow-500/30'
                )}
              >
                {monitorPaused ? '▶' : '⏸'}
                {monitorPaused ? '恢复' : '暂停'}
              </button>
            )}
          </div>
        </div>
      )}

      {sidebarCollapsed && (
        <div className="px-0 pt-4 border-t border-white/10 flex flex-col items-center gap-3">
          <span className={cn('w-2 h-2 rounded-full', browserRunning ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]' : 'bg-slate-500')} title={browserRunning ? '浏览器运行中' : '浏览器未启动'} />
          <span className={cn('w-2 h-2 rounded-full',
            monitorRunning
              ? monitorPaused ? 'bg-yellow-400' : 'bg-emerald-400'
              : 'bg-slate-500'
          )} title={`监控${monitorRunning ? (monitorPaused ? '已暂停' : '运行中') : '未启动'}`} />
        </div>
      )}

      <div className="px-3 mt-4">
        <button
          onClick={toggleSidebar}
          className="flex items-center justify-center w-full py-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
          title={sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'}
        >
          {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>
    </aside>
  )
}
