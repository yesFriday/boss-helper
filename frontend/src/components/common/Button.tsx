import type { ButtonHTMLAttributes } from 'react'
import { forwardRef } from 'react'
import { cn } from '../../lib/cn'

type Variant = 'primary' | 'success' | 'danger' | 'secondary'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

const variantStyles: Record<Variant, string> = {
  primary:
    'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.97]',
  success:
    'bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-md hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.97]',
  danger:
    'bg-gradient-to-r from-red-500 to-red-600 text-white shadow-md hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.97]',
  secondary:
    'bg-slate-100 text-slate-600 hover:bg-slate-200 active:scale-[0.97]',
}

const sizeStyles: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs rounded-lg gap-1',
  md: 'px-5 py-2.5 text-sm rounded-xl gap-1.5',
  lg: 'px-7 py-3.5 text-base rounded-2xl gap-2',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', loading, disabled, className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          'inline-flex items-center justify-center font-semibold transition-all duration-200 ease-out',
          'focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none',
          'disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100',
          variantStyles[variant],
          sizeStyles[size],
          className,
        )}
        {...props}
      >
        {loading && (
          <svg
            className="animate-spin -ml-0.5 h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        )}
        {children}
      </button>
    )
  },
)

Button.displayName = 'Button'