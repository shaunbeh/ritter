import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { sessionsApi } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { formatDate, STATUS_LABELS } from '@/lib/utils'

export function HistoryPage() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['sessions', q, status],
    queryFn: () => sessionsApi.list(q || undefined, status || undefined),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">تاریخچه جلسات</h1>
        <p className="text-sm text-[var(--color-muted)]">جستجو و فیلتر نشست‌های شما</p>
      </div>
      <Card className="flex flex-col gap-3 sm:flex-row">
        <Input
          placeholder="جستجو در عنوان…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="h-10 rounded-xl border border-[var(--color-line)] bg-white px-3 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">همه وضعیت‌ها</option>
          {Object.entries(STATUS_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </Card>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-b border-[var(--color-line)] bg-black/[0.02] text-right">
            <tr>
              <th className="px-4 py-3 font-medium">عنوان</th>
              <th className="px-4 py-3 font-medium">وضعیت</th>
              <th className="px-4 py-3 font-medium">زبان</th>
              <th className="px-4 py-3 font-medium">به‌روزرسانی</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-4 py-6 text-[var(--color-muted)]" colSpan={4}>
                  در حال بارگذاری…
                </td>
              </tr>
            )}
            {!isLoading && (data?.sessions || []).length === 0 && (
              <tr>
                <td className="px-4 py-6 text-[var(--color-muted)]" colSpan={4}>
                  موردی یافت نشد.
                </td>
              </tr>
            )}
            {(data?.sessions || []).map((session) => (
              <tr key={session.id} className="border-b border-[var(--color-line)] last:border-0">
                <td className="px-4 py-3">
                  <Link className="font-medium text-[var(--color-accent)]" to={`/sessions/${session.id}`}>
                    {session.title}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <Badge>{STATUS_LABELS[session.status] || session.status}</Badge>
                </td>
                <td className="px-4 py-3">{session.language || '—'}</td>
                <td className="px-4 py-3 text-[var(--color-muted)]">{formatDate(session.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
