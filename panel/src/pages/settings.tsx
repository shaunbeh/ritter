import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { ApiError, authApi } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const schema = z.object({
  name: z.string().min(1, 'نام لازم است'),
  password: z.string().optional(),
  language: z.string().optional(),
  summarize: z.boolean(),
  diarize: z.boolean(),
})

type FormValues = z.infer<typeof schema>

export function SettingsPage() {
  const { user, setUser } = useAuth()
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const prefs = user?.prefs || {}
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: user?.name || '',
      password: '',
      language: typeof prefs.language === 'string' ? prefs.language : 'fa',
      summarize: prefs.summarize !== false,
      diarize: prefs.diarize !== false,
    },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    setMessage(null)
    setError(null)
    try {
      const updated = await authApi.updateMe({
        name: values.name,
        password: values.password || undefined,
        prefs: {
          language: values.language || 'fa',
          summarize: values.summarize,
          diarize: values.diarize,
        },
      })
      setUser(updated)
      setMessage('تنظیمات ذخیره شد')
      form.setValue('password', '')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'ذخیره ناموفق بود')
    }
  })

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">تنظیمات</h1>
        <p className="text-sm text-[var(--color-muted)]">پروفایل و پیش‌فرض‌های API</p>
      </div>
      <Card>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div>
            <Label htmlFor="name">نام</Label>
            <Input id="name" {...form.register('name')} />
          </div>
          <div>
            <Label htmlFor="email">ایمیل</Label>
            <Input id="email" value={user?.email || ''} disabled />
          </div>
          <div>
            <Label htmlFor="password">رمز عبور جدید</Label>
            <Input id="password" type="password" {...form.register('password')} />
          </div>
          <div>
            <Label htmlFor="language">زبان پیش‌فرض</Label>
            <Input id="language" {...form.register('language')} />
          </div>
          <div className="flex gap-6 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.watch('summarize')}
                onChange={(e) => form.setValue('summarize', e.target.checked)}
              />
              خلاصه‌سازی پیش‌فرض
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.watch('diarize')}
                onChange={(e) => form.setValue('diarize', e.target.checked)}
              />
              تشخیص گوینده پیش‌فرض
            </label>
          </div>
          {message && <p className="text-sm text-[var(--color-accent)]">{message}</p>}
          {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}
          <Button type="submit" disabled={form.formState.isSubmitting}>
            ذخیره
          </Button>
        </form>
      </Card>
    </div>
  )
}
