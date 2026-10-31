import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full bg-black/5 px-2.5 py-0.5 text-xs font-medium text-[var(--color-muted)]',
        className,
      )}
      {...props}
    />
  )
}
