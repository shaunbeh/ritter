import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  authApi,
  clearAuth,
  getStoredUser,
  setAuth,
  setStoredUser,
  type User,
} from '@/lib/api'

type AuthContextValue = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(() => getStoredUser())
  const [loading, setLoading] = useState(true)

  const setUser = useCallback((next: User) => {
    setStoredUser(next)
    setUserState(next)
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const me = await authApi.me()
      setUser(me)
    } catch {
      clearAuth()
      setUserState(null)
    }
  }, [setUser])

  useEffect(() => {
    const existing = getStoredUser()
    if (!existing) {
      setLoading(false)
      return
    }
    void refreshUser().finally(() => setLoading(false))
  }, [refreshUser])

  const login = useCallback(async (email: string, password: string) => {
    const bundle = await authApi.login(email, password)
    setAuth(bundle)
    setUserState(bundle.user)
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout()
    setUserState(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, logout, refreshUser, setUser }),
    [user, loading, login, logout, refreshUser, setUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside provider')
  return ctx
}
