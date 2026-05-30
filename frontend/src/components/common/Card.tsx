import type { HTMLAttributes } from 'react'
import { forwardRef } from 'react'
import { cn } from '../../lib/cn'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hoverable?: boolean
  padded?: boolean
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ hoverable = true, padded = true, className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-2xl bg-white/80 backdrop-blur-sm border border-gray-100 shadow-sm',
          'transition-all duration-300 ease-out',
          hoverable && 'hover:shadow-md hover:-translate-y-0.5 hover:border-gray-200',
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