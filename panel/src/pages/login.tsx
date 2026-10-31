import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '@/lib/auth'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const schema = z.object({
  email: z.string().min(3, 'ایمیل نامعتبر است'),
  password: z.string().min(1, 'رمز عبور لازم است'),
})

type FormValues = z.infer<typeof schema>

export function LoginPage() {
  const { user, login, loading } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  })

  if (!loading && user) return <Navigate to="/" replace />

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    try {
      await login(values.email, values.password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'ورود ناموفق بود')
    }
  })

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <h1 className="mb-1 text-2xl font-bold">ورود به پنل رونویسی</h1>
        <p className="mb-6 text-sm text-[var(--color-muted)]">
          برای دسترسی به تاریخچه جلسات و ضبط زنده وارد شوید.
        </p>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div>
            <Label htmlFor="email">ایمیل</Label>
            <Input id="email" type="email" autoComplete="username" {...form.register('email')} />
          </div>
          <div>
            <Label htmlFor="password">رمز عبور</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...form.register('password')}
            />
          </div>
          {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}
          <Button className="w-full" type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? 'در حال ورود…' : 'ورود'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
