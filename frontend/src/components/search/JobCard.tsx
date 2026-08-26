import { Send, BarChart3, Star } from 'lucide-react'
import type { Job } from '../../api/types'
import { STATUS_MAP, STATUS_BADGE_CLASS, HR_ACTIVE_BADGE_CLASS } from '../../lib/constants'
import { cn } from '../../lib/cn'
import { Button } from '../common/Button'

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
    <div className="flex items-center gap-4 p-4 bg-white rounded-xl border border-slate-200 hover:border-slate-300 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-sm text-slate-900 mb-1">
          {hasUrl ? (
            <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-600 transition-colors">
              {title}
            </a>
          ) : (
            title
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
          {job.company && <span>{job.company}</span>}
          {job.salary && <span className="font-medium text-red-600">{job.salary}</span>}
          {job.city && <span>{job.city}</span>}
          <span className={cn('px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset', STATUS_BADGE_CLASS[status])}>
            {STATUS_MAP[status]}
          </span>
          {job.hr_active_time && (
            <span className={cn('px-2 py-0.5 rounded-md text-xs font-medium border', HR_ACTIVE_BADGE_CLASS[job.hr_active_time] || 'bg-slate-100 text-slate-500 border-slate-200')}>
              {job.hr_active_time}
            </span>
          )}
        </div>
      </div>
      <div className="flex gap-2 flex-shrink-0">
        {(status === 'pending' || status === 'failed') && hasUrl && (
          <Button variant="primary" size="sm" onClick={() => onApply(job.job_url)}>
            <Send size={12} />
            投递
          </Button>
        )}
        <Button variant="secondary" size="sm" onClick={() => onAnalyze(job)}>
          <BarChart3 size={12} />
          分析
        </Button>
        <Button variant="secondary" size="sm" onClick={() => onShortlist(job)}>
          <Star size={12} />
          收藏
        </Button>
      </div>
    </div>
  )
}