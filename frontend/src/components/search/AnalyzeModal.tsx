import { X } from 'lucide-react'
import type { AnalyzeResult } from '../../api/types'
import { Spinner } from '../common/Spinner'
import { cn } from '../../lib/cn'

interface AnalyzeModalProps {
  title: string
  company: string
  result: AnalyzeResult | null
  loading: boolean
  onClose: () => void
}

export function AnalyzeModal({ title, company, result, loading, onClose }: AnalyzeModalProps) {
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-emerald-500'
    if (score >= 60) return 'text-amber-500'
    return 'text-red-500'
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center animate-fade-in" onClick={loading ? undefined : onClose}>
      <div
        className="bg-white rounded-2xl p-6 max-w-lg w-[90%] max-h-[80vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-800">AI 岗位分析</h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer">
            <X size={20} className="text-slate-400" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="lg" />
            <span className="ml-3 text-slate-500">分析中...</span>
          </div>
        ) : result?.error ? (
          <div className="text-red-500 text-center py-8">{result.error}</div>
        ) : result ? (
          <div>
            <div className="text-center mb-6">
              <div className={cn('text-6xl font-extrabold', getScoreColor(result.match_score))}>
                {result.match_score}%
              </div>
              <div className="text-sm text-slate-400 mt-1">匹配度</div>
            </div>

            {result.key_skills?.length > 0 && (
              <div className="mb-4">
                <div className="text-sm font-semibold text-slate-600 mb-2">关键技能</div>
                <div className="flex flex-wrap gap-2">
                  {result.key_skills.map((skill, i) => (
                    <span key={i} className="px-2.5 py-1 bg-indigo-100 text-indigo-700 rounded-full text-xs font-semibold">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {result.gap && (
              <div className="mb-4">
                <div className="text-sm font-semibold text-slate-600 mb-1">差距</div>
                <div className="text-sm text-slate-500">{result.gap}</div>
              </div>
            )}

            {result.advice && (
              <div className="mb-4">
                <div className="text-sm font-semibold text-slate-600 mb-1">建议</div>
                <div className="text-sm text-slate-500">{result.advice}</div>
              </div>
            )}

            {result.summary && (
              <div className="text-xs text-slate-400 mt-4 pt-4 border-t border-slate-100">
                {result.summary}
              </div>
            )}
          </div>
        ) : null}

        <div className="text-xs text-slate-300 mt-4 pt-3 border-t border-slate-100">
          {title} @ {company}
        </div>
      </div>
    </div>
  )
}