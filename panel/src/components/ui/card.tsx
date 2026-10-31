import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface)] p-5 shadow-sm',
        className,
      )}
      {...props}
    />
  )
}
