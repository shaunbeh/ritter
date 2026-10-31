export type User = {
  id: string
  email: string
  name: string
  role: 'admin' | 'user' | string
  prefs: Record<string, unknown>
  created_at?: string
}

export type SessionAsset = {
  id: string
  session_id: string
  kind: string
  object_key: string
  filename?: string | null
  bytes: number
  duration_ms?: number | null
  sort_order: number
  created_at?: string
}

export type Segment = {
  start?: number
  end?: number
  text?: string
  speaker_id?: string
}

export type Session = {
  id: string
  user_id: string
  title: string
  language?: string | null
  status: string
  summarize: boolean
  diarize: boolean
  min_speakers?: number | null
  max_speakers?: number | null
  progress: number
  progress_message?: string | null
  segments?: Segment[] | null
  summary?: string | null
  error?: string | null
  created_at?: string
  updated_at?: string
  assets?: SessionAsset[]
  diarization_error?: string
  summary_error?: string
}

export type FileItem = {
  key: string
  size: number
  last_modified?: string | null
}

type TokenBundle = {
  access_token: string
  refresh_token: string
  user: User
}

const ACCESS_KEY = 'tx_access'
const REFRESH_KEY = 'tx_refresh'
const USER_KEY = 'tx_user'

let accessMemory: string | null = sessionStorage.getItem(ACCESS_KEY)

export function getStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function getAccessToken(): string | null {
  return accessMemory
}

export function setAuth(bundle: TokenBundle) {
  accessMemory = bundle.access_token
  sessionStorage.setItem(ACCESS_KEY, bundle.access_token)
  localStorage.setItem(REFRESH_KEY, bundle.refresh_token)
  localStorage.setItem(USER_KEY, JSON.stringify(bundle.user))
}

export function clearAuth() {
  accessMemory = null
  sessionStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

export function setStoredUser(user: User) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

async function refreshAccess(): Promise<boolean> {
  const refresh = getRefreshToken()
  if (!refresh) return false
  const res = await fetch('/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!res.ok) {
    clearAuth()
    return false
  }
  const data = (await res.json()) as TokenBundle
  setAuth(data)
  return true
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData) && !headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(path, { ...init, headers })
  if (res.status === 401 && retry) {
    const ok = await refreshAccess()
    if (ok) return api<T>(path, init, false)
  }
  if (!res.ok) {
    let detail = 'خطا در ارتباط با سرور'
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'خطا')
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

export const authApi = {
  login: (email: string, password: string) =>
    api<TokenBundle>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: async () => {
    const refresh = getRefreshToken()
    if (refresh && getAccessToken()) {
      try {
        await api('/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refresh }),
        })
      } catch {
        /* ignore */
      }
    }
    clearAuth()
  },
  me: () => api<User>('/auth/me'),
  updateMe: (body: { name?: string; password?: string; prefs?: Record<string, unknown> }) =>
    api<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),
  listUsers: () => api<{ users: User[] }>('/auth/users'),
  createUser: (body: { email: string; name: string; password: string; role: string }) =>
    api<User>('/auth/users', { method: 'POST', body: JSON.stringify(body) }),
}

export const sessionsApi = {
  list: (q?: string, status?: string) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (status) params.set('status', status)
    const qs = params.toString()
    return api<{ sessions: Session[] }>(`/v1/sessions${qs ? `?${qs}` : ''}`)
  },
  create: (body: {
    title: string
    language?: string | null
    summarize?: boolean
    diarize?: boolean
  }) =>
    api<Session>('/v1/sessions', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  get: (id: string) => api<Session>(`/v1/sessions/${id}`),
  update: (id: string, body: Record<string, unknown>) =>
    api<Session>(`/v1/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  remove: (id: string) => api<{ ok: boolean }>(`/v1/sessions/${id}`, { method: 'DELETE' }),
  uploadChunk: async (id: string, blob: Blob, filename: string) => {
    const form = new FormData()
    form.append('file', blob, filename)
    return api<{ asset: SessionAsset }>(`/v1/sessions/${id}/chunks`, {
      method: 'POST',
      body: form,
    })
  },
  uploadSource: async (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api<{ asset: SessionAsset; session: Session }>(`/v1/sessions/${id}/upload`, {
      method: 'POST',
      body: form,
    })
  },
  finalize: (id: string, force = false) =>
    api<Session>(`/v1/sessions/${id}/finalize${force ? '?force=true' : ''}`, {
      method: 'POST',
    }),
  exportUrl: (id: string, format: string) => `/v1/sessions/${id}/export?format=${format}`,
}

export const filesApi = {
  list: () => api<{ files: FileItem[] }>('/v1/files'),
  downloadUrl: (key: string) =>
    `/v1/files/download?key=${encodeURIComponent(key)}`,
}
