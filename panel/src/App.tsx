import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout'
import { useAuth } from '@/lib/auth'
import { AdminUsersPage } from '@/pages/admin-users'
import { DashboardPage } from '@/pages/dashboard'
import { FilesPage } from '@/pages/files'
import { HistoryPage } from '@/pages/history'
import { LivePage } from '@/pages/live'
import { LoginPage } from '@/pages/login'
import { SessionPage } from '@/pages/session'
import { SettingsPage } from '@/pages/settings'
import { UploadPage } from '@/pages/upload'

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-muted)]">
        در حال بارگذاری…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <Protected>
            <AppLayout />
          </Protected>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="live" element={<LivePage />} />
        <Route path="live/:sessionId" element={<LivePage />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="sessions/:id" element={<SessionPage />} />
        <Route path="files" element={<FilesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="admin/users" element={<AdminUsersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
