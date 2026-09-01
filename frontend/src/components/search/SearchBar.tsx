import { useState } from 'react'
import { Search, Zap, Send, Filter, ChevronDown } from 'lucide-react'
import { CITY_GROUPS } from '../../lib/constants'
import { cn } from '../../lib/cn'
import { Button } from '../common/Button'

interface SearchBarProps {
  onSearch: (keyword: string, city: string, welfare?: string, salaryExpect?: number, experienceExpect?: number, excludeHrActive?: string) => void
  onBatchSearch: () => void
  onBatchApply: () => void
  loading: boolean
  isBatchApplying?: boolean
}

const HR_ACTIVE_OPTIONS = [
  { value: '在线', label: '在线' },
  { value: '刚刚活跃', label: '刚刚活跃' },
  { value: '今日活跃', label: '今日活跃' },
  { value: '3日内活跃', label: '3日内活跃' },
  { value: '本周活跃', label: '本周活跃' },
  { value: '本月活跃', label: '本月活跃' },
  { value: '半年前活跃', label: '半年前活跃' },
]

export function SearchBar({ onSearch, onBatchSearch, onBatchApply, loading, isBatchApplying }: SearchBarProps) {
  const [keyword, setKeyword] = useState('AI Agent')
  const [city, setCity] = useState('淄博')
  const [welfare, setWelfare] = useState('')
  const [salaryExpect, setSalaryExpect] = useState('')
  const [experienceExpect, setExperienceExpect] = useState('')
  const [excludeHrActive, setExcludeHrActive] = useState<string[]>([])
  const [showAdvanced, setShowAdvanced] = useState(false)

  const toggleExclude = (val: string) => {
    setExcludeHrActive(prev =>
      prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val]
    )
  }

  const handleSearch = () => {
    onSearch(
      keyword,
      city,
      welfare || undefined,
      salaryExpect ? Number(salaryExpect) : undefined,
      experienceExpect ? Number(experienceExpect) : undefined,
      excludeHrActive.length > 0 ? excludeHrActive.join(',') : undefined,
    )
  }

  return (
    <div className="p-4 bg-white rounded-xl shadow-sm border border-slate-200 mb-5">
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="关键词"
          className="flex-1 min-w-[160px] px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 transition-colors"
        />
        <select
          value={city}
          onChange={(e) => setCity(e.target.value)}
          className="px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 transition-colors cursor-pointer min-w-[100px]"
        >
          {CITY_GROUPS.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.cities.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </optgroup>
          ))}
          <option value="全国">全国</option>
        </select>
        <Button variant="primary" size="md" onClick={handleSearch} disabled={loading || isBatchApplying}>
          <Search size={16} />
          搜索
        </Button>
        <Button variant="secondary" size="md" onClick={onBatchSearch} disabled={loading || isBatchApplying}>
          <Zap size={16} />
          一键搜索
        </Button>
        <Button variant="success" size="md" onClick={onBatchApply} disabled={loading || isBatchApplying}>
          <Send size={16} className={cn(isBatchApplying && 'animate-pulse')} />
          {isBatchApplying ? '投递中...' : '一键投递'}
        </Button>
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border transition-colors cursor-pointer',
            showAdvanced
              ? 'bg-blue-50 text-blue-700 border-blue-300'
              : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
          )}
        >
          <Filter size={14} />
          筛选
          <ChevronDown size={14} className={cn('transition-transform', showAdvanced && 'rotate-180')} />
        </button>
      </div>

      {showAdvanced && (
        <div className="mt-3 pt-3 border-t border-slate-100 space-y-3">
          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              value={welfare}
              onChange={(e) => setWelfare(e.target.value)}
              placeholder="福利:双休,五险一金"
              className="flex-1 min-w-[180px] px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 transition-colors"
            />
            <input
              type="number"
              min="0"
              value={salaryExpect}
              onChange={(e) => setSalaryExpect(e.target.value)}
              placeholder="期望薪资(K)"
              className="w-28 px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 transition-colors"
            />
            <input
              type="number"
              min="0"
              value={experienceExpect}
              onChange={(e) => setExperienceExpect(e.target.value)}
              placeholder="工作年限(年)"
              className="w-28 px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 transition-colors"
            />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400 flex-shrink-0">排除HR状态:</span>
            <div className="flex flex-wrap gap-1.5">
              {HR_ACTIVE_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => toggleExclude(opt.value)}
                  className={cn(
                    'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors cursor-pointer',
                    excludeHrActive.includes(opt.value)
                      ? 'bg-blue-50 border-blue-300 text-blue-700 line-through'
                      : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {excludeHrActive.length > 0 && (
              <span className="text-xs text-slate-400 flex-shrink-0">已排除 {excludeHrActive.length} 项</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
