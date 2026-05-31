import { cn } from '../../lib/cn'

interface ToggleProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
  disabled?: boolean
}

export function Toggle({ enabled, onChange, disabled }: ToggleProps) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={cn(
        'px-4 py-1.5 rounded-lg text-xs font-bold transition-all duration-200 cursor-pointer shadow-sm',
        enabled
          ? 'bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-emerald-200 hover:shadow-md'
          : 'bg-slate-200 text-slate-500 hover:bg-slate-300',
        disabled && 'opacity-40 cursor-not-allowed'
      )}
    >
      {enabled ? '开启' : '关闭'}
    </button>
  )
}
