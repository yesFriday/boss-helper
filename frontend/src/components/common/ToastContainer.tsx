import { useNotificationStore } from '../../stores/notificationStore'
import { X, CheckCircle2, AlertCircle, Info } from 'lucide-react'
import { cn } from '../../lib/cn'

const iconMap = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
}

const colorMap = {
  success: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  error: 'border-red-300 bg-red-50 text-red-800',
  info: 'border-blue-300 bg-blue-50 text-blue-800',
}

export function ToastContainer() {
  const { toasts, removeToast } = useNotificationStore()

  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => {
        const Icon = iconMap[toast.type]
        return (
          <div
            key={toast.id}
            className={cn(
              'pointer-events-auto flex items-center gap-2.5 px-4 py-3 rounded-xl border shadow-lg animate-slide-in',
              'max-w-sm backdrop-blur-sm bg-white/90',
              colorMap[toast.type],
            )}
          >
            <Icon size={18} className="flex-shrink-0" />
            <span className="text-sm font-medium flex-1">{toast.message}</span>
            <button
              onClick={() => removeToast(toast.id)}
              className="flex-shrink-0 p-0.5 rounded hover:bg-black/5 transition-colors cursor-pointer"
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
