import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { Navigate } from 'react-router-dom'
import { ApiError, authApi } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatDate } from '@/lib/utils'

const schema = z.object({
  email: z.string().min(3, 'ایمیل نامعتبر'),
  name: z.string().min(1),
  password: z.string().min(8, 'حداقل ۸ کاراکتر'),
  role: z.enum(['user', 'admin']),
})

type FormValues = z.infer<typeof schema>

export function AdminUsersPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => authApi.listUsers(),
    enabled: user?.role === 'admin',
  })
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', name: '', password: '', role: 'user' },
  })

  if (user && user.role !== 'admin') return <Navigate to="/" replace />

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    try {
      await authApi.createUser(values)
      form.reset({ email: '', name: '', password: '', role: 'user' })
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'ایجاد کاربر ناموفق بود')
    }
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">مدیریت کاربران</h1>
        <p className="text-sm text-[var(--color-muted)]">ایجاد حساب برای همکاران</p>
      </div>

      <Card>
        <h2 className="mb-4 font-semibold">کاربر جدید</h2>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={onSubmit}>
          <div>
            <Label>نام</Label>
            <Input {...form.register('name')} />
          </div>
          <div>
            <Label>ایمیل</Label>
            <Input type="email" {...form.register('email')} />
          </div>
          <div>
            <Label>رمز عبور</Label>
            <Input type="password" {...form.register('password')} />
          </div>
          <div>
            <Label>نقش</Label>
            <select
              className="h-10 w-full rounded-xl border border-[var(--color-line)] bg-white px-3 text-sm"
              {...form.register('role')}
            >
              <option value="user">کاربر</option>
              <option value="admin">مدیر</option>
            </select>
          </div>
          {error && <p className="text-sm text-[var(--color-danger)] sm:col-span-2">{error}</p>}
          <div className="sm:col-span-2">
            <Button type="submit" disabled={form.formState.isSubmitting}>
              ایجاد کاربر
            </Button>
          </div>
        </form>
      </Card>

      <Card className="overflow-x-auto p-0">
        {isLoading && <p className="p-4 text-sm">در حال بارگذاری…</p>}
        <table className="w-full min-w-[560px] text-sm">
          <thead className="border-b border-[var(--color-line)] bg-black/[0.02] text-right">
            <tr>
              <th className="px-4 py-3 font-medium">نام</th>
              <th className="px-4 py-3 font-medium">ایمیل</th>
              <th className="px-4 py-3 font-medium">نقش</th>
              <th className="px-4 py-3 font-medium">ایجاد</th>
            </tr>
          </thead>
          <tbody>
            {(data?.users || []).map((u) => (
              <tr key={u.id} className="border-b border-[var(--color-line)] last:border-0">
                <td className="px-4 py-3">{u.name}</td>
                <td className="px-4 py-3">{u.email}</td>
                <td className="px-4 py-3">{u.role === 'admin' ? 'مدیر' : 'کاربر'}</td>
                <td className="px-4 py-3 text-[var(--color-muted)]">{formatDate(u.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
