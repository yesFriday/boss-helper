import { cn } from '../../lib/cn'

interface FunnelBarProps {
  pending: number
  today: number
  replied: number
  interview: number
}

const items = [
  { key: 'pending', label: '待投递', color: 'bg-amber-400' },
  { key: 'today', label: '已投递', color: 'bg-blue-500' },
  { key: 'replied', label: 'HR回复', color: 'bg-emerald-500' },
  { key: 'interview', label: '面试', color: 'bg-violet-400' },
]

export function FunnelBar({ pending, today, replied, interview }: FunnelBarProps) {
  const values: Record<string, number> = { pending, today, replied, interview }

  return (
    <div className="grid grid-cols-4 gap-4 mb-5">
      {items.map((item) => (
        <div
          key={item.key}
          className="bg-white rounded-xl p-4 text-center border border-slate-200 hover:border-slate-300 transition-colors"
        >
          <div className="text-xl font-semibold text-slate-900">
            {values[item.key] || 0}
          </div>
          <div className="flex items-center justify-center gap-1.5 mt-1">
            <span className={cn('h-1.5 w-1.5 rounded-full flex-shrink-0', item.color)} />
            <span className="text-xs text-slate-400 font-medium">{item.label}</span>
          </div>
        </div>
      ))}
    </div>
  )
}