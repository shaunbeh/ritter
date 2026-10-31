import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Mic, Upload } from 'lucide-react'
import { sessionsApi } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { formatDate, STATUS_LABELS } from '@/lib/utils'

export function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['sessions', 'recent'],
    queryFn: () => sessionsApi.list(),
  })
  const sessions = (data?.sessions || []).slice(0, 8)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">داشبورد</h1>
        <p className="text-sm text-[var(--color-muted)]">شروع سریع ضبط یا آپلود جلسه</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-[var(--color-accent)]/10 p-3 text-[var(--color-accent)]">
              <Mic className="h-5 w-5" />
            </div>
            <div>
              <h2 className="font-semibold">ضبط زنده</h2>
              <p className="text-sm text-[var(--color-muted)]">شروع، توقف موقت و ادامه بعدا</p>
            </div>
          </div>
          <Link to="/live">
            <Button className="w-full">شروع ضبط</Button>
          </Link>
        </Card>
        <Card className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-[var(--color-accent)]/10 p-3 text-[var(--color-accent)]">
              <Upload className="h-5 w-5" />
            </div>
            <div>
              <h2 className="font-semibold">آپلود فایل</h2>
              <p className="text-sm text-[var(--color-muted)]">صوت یا ویدیو را برای رونویسی بفرستید</p>
            </div>
          </div>
          <Link to="/upload">
            <Button className="w-full">آپلود جلسه</Button>
          </Link>
        </Card>
      </div>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">آخرین نشست‌ها</h2>
          <Link to="/history" className="text-sm text-[var(--color-accent)]">
            همه تاریخچه
          </Link>
        </div>
        {isLoading && <p className="text-sm text-[var(--color-muted)]">در حال بارگذاری…</p>}
        {!isLoading && sessions.length === 0 && (
          <p className="text-sm text-[var(--color-muted)]">هنوز نشستی ندارید.</p>
        )}
        <div className="divide-y divide-[var(--color-line)]">
          {sessions.map((session) => (
            <Link
              key={session.id}
              to={`/sessions/${session.id}`}
              className="flex items-center justify-between gap-3 py-3 hover:opacity-80"
            >
              <div>
                <div className="font-medium">{session.title}</div>
                <div className="text-xs text-[var(--color-muted)]">{formatDate(session.updated_at)}</div>
              </div>
              <Badge>{STATUS_LABELS[session.status] || session.status}</Badge>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  )
}
