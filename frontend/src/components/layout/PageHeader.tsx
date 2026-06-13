import { Play, Square } from 'lucide-react'
import { Button } from '../common/Button'
import { useAppStore } from '../../stores/appStore'
import { useSystemStore } from '../../stores/systemStore'
import { systemApi } from '../../api/system'
import { useNotificationStore } from '../../stores/notificationStore'

const pageTitles: Record<string, string> = {
  search: '岗位搜索',
  applications: '投递记录',
  chat: '聊天',
  wechat: '微信记录',
  settings: '设置',
}

export function PageHeader() {
  const { activeTab } = useAppStore()
  const { browserRunning } = useSystemStore()
  const { addToast } = useNotificationStore()

  const handleStart = async () => {
    try {
      const res = await systemApi.startSystem()
      if (res.status === 'started') {
        const status = await systemApi.getStatus()
        useSystemStore.getState().updateFromStatus(status)
        addToast('系统已启动', 'success')
      } else {
        addToast(res.message || '启动失败', 'error')
      }
    } catch {
      addToast('启动失败', 'error')
    }
  }

  const handleStop = async () => {
    await systemApi.stopSystem()
    const status = await systemApi.getStatus()
    useSystemStore.getState().updateFromStatus(status)
    addToast('系统已停止', 'info')
  }

  return (
    <div className="flex items-center justify-between mb-6 p-5 bg-white rounded-xl shadow-sm border border-slate-200">
      <h2 className="text-xl font-bold text-slate-800 tracking-tight">
        {pageTitles[activeTab] || ''}
      </h2>
      <div className="flex gap-2">
        <Button
          onClick={handleStart}
          disabled={browserRunning}
          size="sm"
          variant="success"
        >
          <Play size={14} />
          启动浏览器
        </Button>
        <Button
          onClick={handleStop}
          disabled={!browserRunning}
          size="sm"
          variant="danger"
        >
          <Square size={14} />
          停止
        </Button>
      </div>
    </div>
  )
}