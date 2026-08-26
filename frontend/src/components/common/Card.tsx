import type { HTMLAttributes } from 'react'
import { forwardRef } from 'react'
import { cn } from '../../lib/cn'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hoverable?: boolean
  padded?: boolean
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ hoverable = false, padded = true, className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-xl bg-white border border-slate-200',
          'transition-shadow duration-150 ease-out',
          hoverable && 'hover:shadow-sm',
          padded && 'p-5',
          className,
        )}
        {...props}
      >
        {children}
      </div>
    )
  },
)

Card.displayName = 'Card'
