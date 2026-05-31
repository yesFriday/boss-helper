import { useState, useRef, useEffect } from 'react'
import { cn } from '../../lib/cn'

interface TimePickerProps {
  value: string // "HH:MM"
  onChange: (value: string) => void
  className?: string
}

const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = Array.from({ length: 60 }, (_, i) => i)

function pad(n: number) {
  return String(n).padStart(2, '0')
}

export function TimePicker({ value, onChange, className }: TimePickerProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const [h, m] = (value || '09:00').split(':').map(Number)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm font-mono',
          'outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all cursor-pointer',
          'hover:bg-slate-100 min-w-[72px] text-center',
          open && 'border-indigo-500 ring-2 ring-indigo-500/20',
          className
        )}
      >
        {pad(h)}:{pad(m)}
      </button>

      {open && (
        <div className="absolute z-50 top-full left-0 mt-1 bg-white rounded-xl shadow-lg border border-slate-200 p-3 flex gap-3">
          {/* 小时列 */}
          <div className="flex flex-col">
            <div className="text-xs font-semibold text-slate-400 text-center mb-1.5">时</div>
            <div className="h-52 overflow-y-auto w-12 flex flex-col gap-0.5 scrollbar-thin">
              {HOURS.map((hour) => (
                <button
                  key={hour}
                  type="button"
                  onClick={() => {
                    onChange(`${pad(hour)}:${pad(m)}`)
                  }}
                  className={cn(
                    'py-1 text-sm rounded-md transition-colors cursor-pointer text-center',
                    hour === h
                      ? 'bg-indigo-500 text-white font-semibold'
                      : 'text-slate-600 hover:bg-indigo-50'
                  )}
                >
                  {pad(hour)}
                </button>
              ))}
            </div>
          </div>

          {/* 分钟列 */}
          <div className="flex flex-col">
            <div className="text-xs font-semibold text-slate-400 text-center mb-1.5">分</div>
            <div className="h-52 overflow-y-auto w-12 flex flex-col gap-0.5 scrollbar-thin">
              {MINUTES.map((minute) => (
                <button
                  key={minute}
                  type="button"
                  onClick={() => {
                    onChange(`${pad(h)}:${pad(minute)}`)
                  }}
                  className={cn(
                    'py-1 text-sm rounded-md transition-colors cursor-pointer text-center',
                    minute === m
                      ? 'bg-indigo-500 text-white font-semibold'
                      : 'text-slate-600 hover:bg-indigo-50'
                  )}
                >
                  {pad(minute)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
