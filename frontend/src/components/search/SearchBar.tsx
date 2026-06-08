import { useState } from 'react'
import { Search, Zap, Send, Filter } from 'lucide-react'
import { CITY_GROUPS } from '../../lib/constants'

interface SearchBarProps {
  onSearch: (keyword: string, city: string, welfare?: string, salaryExpect?: number, experienceExpect?: number, excludeHrActive?: string) => void
  onBatchSearch: () => void
  onBatchApply: () => void
  loading: boolean
}

const HR_ACTIVE_OPTIONS = [
  { value: '半年前活跃', label: '半年前活跃' },
  { value: '一年前活跃', label: '一年前活跃' },
]

export function SearchBar({ onSearch, onBatchSearch, onBatchApply, loading }: SearchBarProps) {
  const [keyword, setKeyword] = useState('AI Agent')
  const [city, setCity] = useState('淄博')
  const [welfare, setWelfare] = useState('')
  const [salaryExpect, setSalaryExpect] = useState('')
  const [experienceExpect, setExperienceExpect] = useState('')
  const [excludeHrActive, setExcludeHrActive] = useState<string[]>([])

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
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="关键词"
          className="flex-1 min-w-[160px] px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
        />
        <select
          value={city}
          onChange={(e) => setCity(e.target.value)}
          className="px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 cursor-pointer min-w-[100px]"
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
        <input
          type="text"
          value={welfare}
          onChange={(e) => setWelfare(e.target.value)}
          placeholder="福利:双休,五险一金"
          className="w-40 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
        />
        <input
          type="number"
          min="0"
          value={salaryExpect}
          onChange={(e) => setSalaryExpect(e.target.value)}
          placeholder="期望薪资(K)"
          className="w-28 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
        />
        <input
          type="number"
          min="0"
          value={experienceExpect}
          onChange={(e) => setExperienceExpect(e.target.value)}
          placeholder="工作年限(年)"
          className="w-28 px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-500 shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 disabled:opacity-50 cursor-pointer"
        >
          <Search size={16} />
          搜索
        </button>
        <button
          onClick={onBatchSearch}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-amber-500 to-orange-500 shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
        >
          <Zap size={16} />
          一键搜索
        </button>
        <button
          onClick={onBatchApply}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-emerald-500 to-teal-500 shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
        >
          <Send size={16} />
          一键投递
        </button>
      </div>
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-slate-100">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Filter size={13} />
          排除HR状态:
        </div>
        {HR_ACTIVE_OPTIONS.map(opt => (
          <button
            key={opt.value}
            onClick={() => toggleExclude(opt.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all cursor-pointer ${
              excludeHrActive.includes(opt.value)
                ? 'bg-red-50 border-red-300 text-red-600 line-through'
                : 'bg-slate-50 border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-600'
            }`}
          >
            {opt.label}
          </button>
        ))}
        {excludeHrActive.length > 0 && (
          <span className="text-xs text-red-400">已排除 {excludeHrActive.length} 项</span>
        )}
      </div>
    </div>
  )
}