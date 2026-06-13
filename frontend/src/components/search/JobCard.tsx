import { Send, BarChart3, Star } from 'lucide-react'
import type { Job } from '../../api/types'
import { STATUS_MAP, STATUS_BADGE_CLASS, HR_ACTIVE_BADGE_CLASS } from '../../lib/constants'
import { cn } from '../../lib/cn'

interface JobCardProps {
  job: Job
  onApply: (url: string) => void
  onAnalyze: (job: Job) => void
  onShortlist: (job: Job) => void
}

export function JobCard({ job, onApply, onAnalyze, onShortlist }: JobCardProps) {
  const hasUrl = !!job.job_url
  const status = job.status || (hasUrl ? 'pending' : 'missing_url')
  const title = job.job_title || job.title || '未知'

  return (
    <div className="flex items-center gap-4 p-4 bg-white rounded-xl shadow-sm border border-slate-200 hover:shadow-md hover:-translate-y-0.5 hover:border-indigo-300 transition-all duration-200">
      <div className="flex-1 min-w-0">
        <div className="font-bold text-sm text-slate-800 mb-1">
          {hasUrl ? (
            <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="hover:text-indigo-600 transition-colors">
              {title}
            </a>
          ) : (
            title
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          {job.company && <span>{job.company}</span>}
          {job.salary && <span className="font-bold text-red-500">{job.salary}</span>}
          {job.city && <span>{job.city}</span>}
          <span className={cn('px-2 py-0.5 rounded-full text-xs font-semibold', STATUS_BADGE_CLASS[status])}>
            {STATUS_MAP[status]}
          </span>
          {job.hr_active_time && (
            <span className={cn('px-2 py-0.5 rounded-full text-xs font-semibold border', HR_ACTIVE_BADGE_CLASS[job.hr_active_time] || 'bg-gray-100 text-gray-500 border-gray-200')}>
              {job.hr_active_time}
            </span>
          )}
        </div>
      </div>
      <div className="flex gap-2 flex-shrink-0">
        {(status === 'pending' || status === 'failed') && hasUrl && (
          <button
            onClick={() => onApply(job.job_url)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-indigo-500 to-purple-500 shadow-sm hover:shadow-md transition-all cursor-pointer"
          >
            <Send size={12} />
            投递
          </button>
        )}
        <button
          onClick={() => onAnalyze(job)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
        >
          <BarChart3 size={12} />
          分析
        </button>
        <button
          onClick={() => onShortlist(job)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-colors cursor-pointer"
        >
          <Star size={12} />
          收藏
        </button>
      </div>
    </div>
  )
}