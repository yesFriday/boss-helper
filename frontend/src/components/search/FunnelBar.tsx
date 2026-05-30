import { cn } from '../../lib/cn'

interface FunnelBarProps {
  pending: number
  today: number
  replied: number
  interview: number
}

const items = [
  { key: 'pending', label: '待投递', color: 'from-amber-400 to-orange-400' },
  { key: 'today', label: '已投递', color: 'from-indigo-400 to-purple-400' },
  { key: 'replied', label: 'HR回复', color: 'from-emerald-400 to-teal-400' },
  { key: 'interview', label: '面试', color: 'from-pink-400 to-rose-400' },
]

export function FunnelBar({ pending, today, replied, interview }: FunnelBarProps) {
  const values: Record<string, number> = { pending, today, replied, interview }

  return (
    <div className="grid grid-cols-4 gap-4 mb-5">
      {items.map((item) => (
        <div
          key={item.key}
          className="bg-white rounded-xl p-4 text-center shadow-sm border border-slate-200 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200"
        >
          <div className={cn('text-3xl font-extrabold bg-gradient-to-r bg-clip-text text-transparent', item.color)}>
            {values[item.key] || 0}
          </div>
          <div className="text-xs text-slate-400 mt-1 font-semibold uppercase tracking-wider">
            {item.label}
          </div>
        </div>
      ))}
    </div>
  )
}