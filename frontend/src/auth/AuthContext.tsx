import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, get, post } from '../api/client'
import type { AuthOut, User } from '../api/types'

interface AuthCtx {
  user: User | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName: string) => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    get<User>('/auth/me')
      .then(setUser)
      .catch((e) => {
        if (!(e instanceof ApiError) || e.status !== 401) console.warn('session check failed', e)
      })
      .finally(() => setReady(true))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setUser((await post<AuthOut>('/auth/login', { email, password })).user)
  }, [])
  const register = useCallback(async (email: string, password: string, display_name: string) => {
    setUser((await post<AuthOut>('/auth/register', { email, password, display_name })).user)
  }, [])
  const logout = useCallback(async () => {
    await post('/auth/logout')
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, ready, login, register, logout }), [user, ready, login, register, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used inside AuthProvider')
  return c
}
