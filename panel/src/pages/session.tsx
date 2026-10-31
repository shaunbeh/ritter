import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getAccessToken, sessionsApi } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { formatDate, formatBytes, STATUS_LABELS } from '@/lib/utils'

async function downloadAuthed(url: string, filename: string) {
  const token = getAccessToken()
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error('دانلود ناموفق')
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}

function formatTs(seconds?: number) {
  const total = Math.max(0, Math.floor(seconds || 0))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function SessionPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const { data: session, isLoading, error } = useQuery({
    queryKey: ['session', id],
    queryFn: () => sessionsApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status === 'queued' || status === 'processing' ? 1000 : false
    },
  })

  if (isLoading) return <p className="text-sm text-[var(--color-muted)]">در حال بارگذاری…</p>
  if (error || !session) return <p className="text-sm text-[var(--color-danger)]">نشست یافت نشد</p>

  const processing = session.status === 'queued' || session.status === 'processing'
  const downloading =
    processing &&
    Boolean(
      session.progress_message &&
        (session.progress_message.includes('دانلود') ||
          session.progress_message.toLowerCase().includes('download') ||
          session.progress_message.includes('هم‌ترازی')),
    )
  const canReprocess = (session.assets?.length || 0) > 0

  const reprocess = async (force = false) => {
    await sessionsApi.finalize(id, force)
    await queryClient.invalidateQueries({ queryKey: ['session', id] })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{session.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-[var(--color-muted)]">
            <Badge>{STATUS_LABELS[session.status] || session.status}</Badge>
            <span>{session.language || 'خودکار'}</span>
            <span>{formatDate(session.updated_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {(session.status === 'draft' || session.status === 'recording') && (
            <Link to={`/live/${session.id}`}>
              <Button variant="secondary">ادامه ضبط</Button>
            </Link>
          )}
          {session.status === 'completed' && (
            <>
              <Button
                variant="secondary"
                onClick={() => void downloadAuthed(sessionsApi.exportUrl(id, 'txt'), `${session.title}.txt`)}
              >
                TXT
              </Button>
              <Button
                variant="secondary"
                onClick={() => void downloadAuthed(sessionsApi.exportUrl(id, 'srt'), `${session.title}.srt`)}
              >
                SRT
              </Button>
              <Button
                variant="secondary"
                onClick={() => void downloadAuthed(sessionsApi.exportUrl(id, 'json'), `${session.title}.json`)}
              >
                JSON
              </Button>
            </>
          )}
          {canReprocess &&
            (session.status === 'failed' ||
              session.status === 'completed' ||
              session.status === 'draft') && (
              <Button onClick={() => void reprocess(false)}>پردازش دوباره</Button>
            )}
          {canReprocess && processing && (
            <Button variant="secondary" onClick={() => void reprocess(true)}>
              قطع و تلاش دوباره
            </Button>
          )}
        </div>
      </div>

      {processing && (
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">
              {downloading ? 'در حال دانلود مدل از Hugging Face' : 'وضعیت پردازش'}
            </span>
            <span className="tabular-nums text-[var(--color-muted)]">{session.progress || 0}٪</span>
          </div>
          <Progress value={session.progress || 0} />
          <p className="text-sm leading-6">{session.progress_message}</p>
          {downloading && (
            <p className="text-xs text-[var(--color-muted)]">
              اولین اجرای زبان فارسی مدل هم‌ترازی (~۱٫۲ گیگ) را می‌گیرد. پیشرفت هر ثانیه
              به‌روز می‌شود. اگر متوقف ماند، «قطع و تلاش دوباره» را بزنید.
            </p>
          )}
        </Card>
      )}

      {session.error && (
        <Card className="border-red-200 bg-red-50 text-sm text-[var(--color-danger)]">{session.error}</Card>
      )}

      {session.diarization_error && (
        <Card className="border-amber-200 bg-amber-50 text-sm text-[var(--color-warn)]">
          تشخیص گوینده انجام نشد: {session.diarization_error}
        </Card>
      )}

      {session.summary && (
        <Card>
          <h2 className="mb-2 font-semibold">خلاصه</h2>
          <p className="whitespace-pre-wrap text-sm leading-7">{session.summary}</p>
          {session.summary_error && (
            <p className="mt-2 text-xs text-[var(--color-warn)]">{session.summary_error}</p>
          )}
        </Card>
      )}

      <Card>
        <h2 className="mb-3 font-semibold">رونوشت</h2>
        {!session.segments?.length && (
          <p className="text-sm text-[var(--color-muted)]">هنوز متنی آماده نیست.</p>
        )}
        <div className="space-y-3">
          {(session.segments || []).map((seg, idx) => (
            <div key={idx} className="rounded-xl bg-black/[0.03] p-3 text-sm">
              <div className="mb-1 flex gap-2 text-xs text-[var(--color-muted)]">
                <span>{seg.speaker_id || 'گوینده'}</span>
                <span>
                  {formatTs(seg.start)} – {formatTs(seg.end)}
                </span>
              </div>
              <div className="leading-7">{seg.text}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 font-semibold">فایل‌های نشست</h2>
        <div className="divide-y divide-[var(--color-line)]">
          {(session.assets || []).map((asset) => (
            <div key={asset.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div>
                <div className="font-medium">{asset.filename || asset.object_key}</div>
                <div className="text-xs text-[var(--color-muted)]">
                  {asset.kind} · {formatBytes(asset.bytes)}
                </div>
              </div>
            </div>
          ))}
          {(session.assets || []).length === 0 && (
            <p className="text-sm text-[var(--color-muted)]">فایلی ثبت نشده است.</p>
          )}
        </div>
      </Card>
    </div>
  )
}
