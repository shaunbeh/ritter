import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Pause, Play, Square } from 'lucide-react'
import { ApiError, sessionsApi, type Session } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { STATUS_LABELS } from '@/lib/utils'

type RecState = 'idle' | 'recording' | 'paused' | 'uploading' | 'finalizing'

function prefsDefaults(prefs: Record<string, unknown>) {
  return {
    language: typeof prefs.language === 'string' ? prefs.language : 'fa',
    summarize: prefs.summarize !== false,
    diarize: prefs.diarize !== false,
  }
}

export function LivePage() {
  const { sessionId } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const defaults = prefsDefaults(user?.prefs || {})

  const [title, setTitle] = useState(`جلسه ${new Date().toLocaleString('fa-IR')}`)
  const [language, setLanguage] = useState(defaults.language)
  const [summarize, setSummarize] = useState(defaults.summarize)
  const [diarize, setDiarize] = useState(defaults.diarize)
  const [session, setSession] = useState<Session | null>(null)
  const [recState, setRecState] = useState<RecState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [chunkCount, setChunkCount] = useState(0)
  const [secureOk] = useState(() => window.isSecureContext)

  const mediaRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const sessionIdRef = useRef<string | null>(sessionId || null)
  const partsRef = useRef<Blob[]>([])

  const activeId = sessionId || session?.id

  const sessionQuery = useQuery({
    queryKey: ['session', activeId],
    queryFn: () => sessionsApi.get(activeId!),
    enabled: Boolean(activeId),
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status === 'queued' || status === 'processing' ? 2000 : false
    },
  })

  useEffect(() => {
    if (sessionQuery.data) {
      setSession(sessionQuery.data)
      setTitle(sessionQuery.data.title)
      setChunkCount(sessionQuery.data.assets?.filter((a) => a.kind === 'chunk').length || 0)
    }
  }, [sessionQuery.data])

  const ensureSession = useCallback(async () => {
    if (sessionIdRef.current) {
      const existing = await sessionsApi.get(sessionIdRef.current)
      setSession(existing)
      return existing
    }
    const created = await sessionsApi.create({
      title: title.trim() || 'جلسه بدون عنوان',
      language: language || null,
      summarize,
      diarize,
    })
    sessionIdRef.current = created.id
    setSession(created)
    navigate(`/live/${created.id}`, { replace: true })
    return created
  }, [title, language, summarize, diarize, navigate])

  const uploadBlob = useCallback(async (blob: Blob) => {
    const id = sessionIdRef.current
    if (!id || blob.size === 0) return
    setRecState('uploading')
    await sessionsApi.uploadChunk(id, blob, `chunk-${Date.now()}.webm`)
    setChunkCount((c) => c + 1)
    await queryClient.invalidateQueries({ queryKey: ['session', id] })
  }, [queryClient])

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    mediaRef.current = null
  }

  const startRecording = async () => {
    setError(null)
    if (!secureOk) {
      setError('برای دسترسی به میکروفون به HTTPS یا localhost نیاز است.')
      return
    }
    try {
      await ensureSession()
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      const recorder = new MediaRecorder(stream, { mimeType: mime })
      partsRef.current = []
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) partsRef.current.push(ev.data)
      }
      recorder.start(5000)
      mediaRef.current = recorder
      await sessionsApi.update(sessionIdRef.current!, { status: 'recording' })
      setRecState('recording')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'شروع ضبط ناموفق بود')
      stopTracks()
      setRecState('idle')
    }
  }

  const pauseRecording = async () => {
    const recorder = mediaRef.current
    if (!recorder || recorder.state !== 'recording') return
    recorder.requestData()
    recorder.pause()
    setRecState('paused')
    const blob = new Blob(partsRef.current, { type: recorder.mimeType })
    partsRef.current = []
    try {
      await uploadBlob(blob)
      setRecState('paused')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'آپلود تکه ناموفق بود')
      setRecState('paused')
    }
  }

  const resumeRecording = () => {
    const recorder = mediaRef.current
    if (!recorder || recorder.state !== 'paused') return
    recorder.resume()
    setRecState('recording')
  }

  const finalize = async () => {
    setError(null)
    try {
      const recorder = mediaRef.current
      if (recorder && recorder.state !== 'inactive') {
        await new Promise<void>((resolve) => {
          recorder.onstop = () => resolve()
          recorder.requestData()
          recorder.stop()
        })
        const blob = new Blob(partsRef.current, { type: recorder.mimeType })
        partsRef.current = []
        await uploadBlob(blob)
      }
      stopTracks()
      const id = sessionIdRef.current
      if (!id) return
      setRecState('finalizing')
      const updated = await sessionsApi.finalize(id)
      setSession(updated)
      await queryClient.invalidateQueries({ queryKey: ['session', id] })
      navigate(`/sessions/${id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'نهایی‌سازی ناموفق بود')
      setRecState('paused')
    }
  }

  useEffect(() => () => stopTracks(), [])

  const status = session?.status || 'draft'
  const processing = status === 'queued' || status === 'processing'

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">ضبط زنده</h1>
        <p className="text-sm text-[var(--color-muted)]">
          ضبط را متوقف کنید، بعدا ادامه دهید، سپس برای رونویسی نهایی کنید.
        </p>
      </div>

      <Card className="space-y-4">
        <div>
          <Label htmlFor="title">عنوان جلسه</Label>
          <Input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={recState === 'recording' || processing}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <Label htmlFor="lang">زبان</Label>
            <Input id="lang" value={language} onChange={(e) => setLanguage(e.target.value)} />
          </div>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input type="checkbox" checked={summarize} onChange={(e) => setSummarize(e.target.checked)} />
            خلاصه‌سازی
          </label>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input type="checkbox" checked={diarize} onChange={(e) => setDiarize(e.target.checked)} />
            تشخیص گوینده
          </label>
        </div>

        {!secureOk && (
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-[var(--color-warn)]">
            میکروفون فقط در HTTPS یا localhost در دسترس است.
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          {recState === 'idle' || recState === 'paused' ? (
            recState === 'paused' ? (
              <Button onClick={resumeRecording}>
                <Play className="h-4 w-4" />
                ادامه ضبط
              </Button>
            ) : (
              <Button onClick={() => void startRecording()}>
                <Play className="h-4 w-4" />
                شروع ضبط
              </Button>
            )
          ) : null}
          {recState === 'recording' && (
            <Button variant="secondary" onClick={() => void pauseRecording()}>
              <Pause className="h-4 w-4" />
              توقف موقت
            </Button>
          )}
          {(recState === 'recording' || recState === 'paused' || chunkCount > 0) && !processing && (
            <Button variant="danger" onClick={() => void finalize()} disabled={recState === 'uploading'}>
              <Square className="h-4 w-4" />
              نهایی و رونویسی
            </Button>
          )}
        </div>

        <div className="text-sm text-[var(--color-muted)]">
          وضعیت ضبط: {recState} · تکه‌ها: {chunkCount} · نشست: {STATUS_LABELS[status] || status}
        </div>
        {processing && session && (
          <div className="space-y-2">
            <Progress value={session.progress || 0} />
            <p className="text-sm">{session.progress_message}</p>
          </div>
        )}
        {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}
        {activeId && (
          <Link className="text-sm text-[var(--color-accent)]" to={`/sessions/${activeId}`}>
            مشاهده جزئیات نشست
          </Link>
        )}
      </Card>
    </div>
  )
}
