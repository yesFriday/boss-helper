import { useState, useEffect, useRef } from 'react'
import { Smartphone, Copy, RefreshCw } from 'lucide-react'
import { Button } from '../components/common/Button'
import { EmptyState } from '../components/common/EmptyState'
import { useNotificationStore } from '../stores/notificationStore'
import { wechatApi } from '../api/wechat'
import { formatDate } from '../lib/utils'
import type { WechatExchange } from '../api/types'

export function WechatPage() {
  const [exchanges, setExchanges] = useState<WechatExchange[]>([])
  const { addToast } = useNotificationStore()
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    loadExchanges()
    timerRef.current = window.setInterval(loadExchanges, 30000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const loadExchanges = async () => {
    try {
      const res = await wechatApi.getWechatExchanges()
      setExchanges(res.exchanges || [])
    } catch {}
  }

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      addToast('已复制', 'success')
    } catch {
      addToast('复制失败', 'error')
    }
  }

  return (
    <div className="animate-slide-in">
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-lg font-semibold text-slate-900">已获取的 HR 微信</h3>
        <button
          onClick={loadExchanges}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 bg-white border border-slate-200 hover:border-slate-300 transition-colors cursor-pointer"
        >
          <RefreshCw size={12} />
          刷新
        </button>
      </div>

      {exchanges.length > 0 ? (
        <div className="flex flex-col gap-4">
          {exchanges.map((ex, i) => (
            <div
              key={i}
              className="rounded-xl bg-white border border-slate-200 p-4"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="font-medium text-slate-900 mb-2">{ex.hr_name}</div>
                  {ex.job_description && (
                    <div className="text-xs text-slate-500 mb-3 p-3 bg-slate-50 rounded-md leading-relaxed">
                      {ex.job_description}
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    <code className="font-mono text-sm text-slate-700 bg-slate-50 rounded-md px-2.5 py-1">
                      {ex.hr_wechat}
                    </code>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleCopy(ex.hr_wechat)}
                    >
                      <Copy size={12} />
                      复制
                    </Button>
                  </div>
                </div>
                <div className="text-xs text-slate-400 text-right ml-4">
                  {ex.hr_company}
                  <br />
                  {formatDate(ex.wechat_shared_at)}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Smartphone size={48} className="text-slate-300" />}
          title="暂无微信记录"
          description="当 HR 分享微信时会自动记录在这里"
        />
      )}
    </div>
  )
}