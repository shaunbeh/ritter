import { useQuery } from '@tanstack/react-query'
import { filesApi, getAccessToken } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { formatBytes, formatDate } from '@/lib/utils'

async function downloadFile(key: string) {
  const token = getAccessToken()
  const res = await fetch(filesApi.downloadUrl(key), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error('دانلود ناموفق')
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = key.split('/').pop() || 'file'
  a.click()
  URL.revokeObjectURL(href)
}

export function FilesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['files'],
    queryFn: () => filesApi.list(),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">کتابخانه فایل</h1>
        <p className="text-sm text-[var(--color-muted)]">اشیای ذخیره‌شده شما در MinIO</p>
      </div>
      <Card className="overflow-x-auto p-0">
        {isLoading && <p className="p-4 text-sm text-[var(--color-muted)]">در حال بارگذاری…</p>}
        {error && <p className="p-4 text-sm text-[var(--color-danger)]">خطا در دریافت فهرست</p>}
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-b border-[var(--color-line)] bg-black/[0.02] text-right">
            <tr>
              <th className="px-4 py-3 font-medium">کلید</th>
              <th className="px-4 py-3 font-medium">حجم</th>
              <th className="px-4 py-3 font-medium">تاریخ</th>
              <th className="px-4 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {(data?.files || []).map((file) => (
              <tr key={file.key} className="border-b border-[var(--color-line)] last:border-0">
                <td className="max-w-md truncate px-4 py-3" title={file.key}>
                  {file.key}
                </td>
                <td className="px-4 py-3">{formatBytes(file.size)}</td>
                <td className="px-4 py-3 text-[var(--color-muted)]">{formatDate(file.last_modified)}</td>
                <td className="px-4 py-3">
                  <Button size="sm" variant="secondary" onClick={() => void downloadFile(file.key)}>
                    دانلود
                  </Button>
                </td>
              </tr>
            ))}
            {!isLoading && (data?.files || []).length === 0 && (
              <tr>
                <td className="px-4 py-6 text-[var(--color-muted)]" colSpan={4}>
                  فایلی وجود ندارد.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
