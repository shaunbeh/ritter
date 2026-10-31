import { NavLink, Outlet } from 'react-router-dom'
import {
  FileAudio,
  FolderOpen,
  History,
  LayoutDashboard,
  LogOut,
  Mic,
  Settings,
  Upload,
  Users,
} from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const links = [
  { to: '/', label: 'داشبورد', icon: LayoutDashboard, end: true },
  { to: '/live', label: 'ضبط زنده', icon: Mic },
  { to: '/upload', label: 'آپلود', icon: Upload },
  { to: '/history', label: 'تاریخچه', icon: History },
  { to: '/files', label: 'فایل‌ها', icon: FolderOpen },
  { to: '/settings', label: 'تنظیمات', icon: Settings },
]

export function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl gap-6 p-4 md:p-6">
      <aside className="sticky top-4 hidden h-[calc(100vh-2rem)] w-60 shrink-0 flex-col rounded-3xl border border-[var(--color-line)] bg-[var(--color-surface)] p-4 md:flex">
        <div className="mb-6 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--color-accent)] text-[var(--color-accent-fg)]">
            <FileAudio className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-bold">پنل رونویسی</div>
            <div className="text-xs text-[var(--color-muted)]">یادداشت جلسات</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition',
                  isActive
                    ? 'bg-[var(--color-accent)] text-[var(--color-accent-fg)]'
                    : 'text-[var(--color-ink)] hover:bg-black/5',
                )
              }
            >
              <link.icon className="h-4 w-4" />
              {link.label}
            </NavLink>
          ))}
          {user?.role === 'admin' && (
            <NavLink
              to="/admin/users"
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition',
                  isActive
                    ? 'bg-[var(--color-accent)] text-[var(--color-accent-fg)]'
                    : 'text-[var(--color-ink)] hover:bg-black/5',
                )
              }
            >
              <Users className="h-4 w-4" />
              کاربران
            </NavLink>
          )}
        </nav>
        <div className="mt-4 border-t border-[var(--color-line)] pt-4">
          <div className="mb-3 px-2 text-sm">
            <div className="font-medium">{user?.name}</div>
            <div className="text-xs text-[var(--color-muted)]">{user?.email}</div>
          </div>
          <Button variant="secondary" className="w-full" onClick={() => void logout()}>
            <LogOut className="h-4 w-4" />
            خروج
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <header className="flex items-center justify-between rounded-2xl border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3 md:hidden">
          <div className="font-bold">پنل رونویسی</div>
          <Button variant="ghost" size="sm" onClick={() => void logout()}>
            خروج
          </Button>
        </header>
        <nav className="flex gap-2 overflow-x-auto md:hidden">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                cn(
                  'whitespace-nowrap rounded-full px-3 py-1.5 text-xs',
                  isActive ? 'bg-[var(--color-accent)] text-white' : 'bg-white border',
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
