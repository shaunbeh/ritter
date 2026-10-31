import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, sessionsApi } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function UploadPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const prefs = user?.prefs || {}
  const [title, setTitle] = useState(`آپلود ${new Date().toLocaleString('fa-IR')}`)
  const [language, setLanguage] = useState(
    typeof prefs.language === 'string' ? prefs.language : 'fa',
  )
  const [summarize, setSummarize] = useState(prefs.summarize !== false)
  const [diarize, setDiarize] = useState(prefs.diarize !== false)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      setError('فایل را انتخاب کنید')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const session = await sessionsApi.create({
        title: title.trim() || file.name,
        language: language || null,
        summarize,
        diarize,
      })
      await sessionsApi.uploadSource(session.id, file)
      const finalized = await sessionsApi.finalize(session.id)
      navigate(`/sessions/${finalized.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'آپلود ناموفق بود')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">آپلود فایل</h1>
        <p className="text-sm text-[var(--color-muted)]">فایل صوتی یا ویدیویی را برای رونویسی بفرستید</p>
      </div>
      <Card>
        <form className="space-y-4" onSubmit={(e) => void onSubmit(e)}>
          <div>
            <Label htmlFor="title">عنوان</Label>
            <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="lang">زبان</Label>
            <Input id="lang" value={language} onChange={(e) => setLanguage(e.target.value)} />
          </div>
          <div className="flex gap-6 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={summarize} onChange={(e) => setSummarize(e.target.checked)} />
              خلاصه‌سازی
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={diarize} onChange={(e) => setDiarize(e.target.checked)} />
              تشخیص گوینده
            </label>
          </div>
          <div>
            <Label htmlFor="file">فایل</Label>
            <Input
              id="file"
              type="file"
              accept="audio/*,video/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </div>
          {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? 'در حال ارسال…' : 'آپلود و صف پردازش'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
