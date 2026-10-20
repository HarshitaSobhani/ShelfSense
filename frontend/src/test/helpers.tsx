import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AppRoutes } from '../App'
import { AuthProvider } from '../auth/AuthContext'
import type { Book, User } from '../api/types'

export type Handler = (req: { method: string; path: string; params: URLSearchParams; body: unknown }) => { status?: number; json?: unknown } | undefined

export const calls: { method: string; path: string; params: URLSearchParams; body: unknown; headers: Record<string, string> }[] = []

export function mockFetch(handler: Handler, user: User | null = null) {
  calls.length = 0
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const path = url.pathname.replace('/api/v1', '')
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method, path, params: url.searchParams, body, headers: (init?.headers ?? {}) as Record<string, string> })
    let r = handler({ method, path, params: url.searchParams, body })
    if (!r && path === '/auth/me') r = user ? { json: user } : { status: 401, json: { error: { code: 'unauthorized', message: 'Authentication required' } } }
    if (!r) r = { status: 404, json: { error: { code: 'not_found', message: `unmocked ${method} ${path}` } } }
    const status = r.status ?? 200
    return new Response(status === 204 ? null : JSON.stringify(r.json ?? {}), { status, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

export const USER: User = { id: 1, email: 'reader@example.com', display_name: 'Reader', is_admin: false }
export const ADMIN: User = { ...USER, id: 2, email: 'admin@example.com', display_name: 'Admin', is_admin: true }

export function book(over: Partial<Book> = {}): Book {
  return {
    id: 1, slug: 'rebecca-1938', title: 'Rebecca', subtitle: null, description: 'A young bride and a haunted manor.',
    first_publish_year: 1938, page_count: 400, cover_url: null, pacing: 'medium', authors: ['Daphne du Maurier'],
    genres: ['gothic'], moods: ['atmospheric'], tropes: ['haunted house'], content_warnings: [], source: 'seed', has_embedding: true, ...over,
  }
}

export const meta = (over = {}) => ({ page: 1, page_size: 12, total: 1, pages: 1, ...over })
export const searchMeta = (over = {}) => ({ ...meta(), mode_used: 'hybrid', semantic_available: true, notice: null, books_without_embeddings: 0, cold_start: false, ...over })
export const facets = {
  genres: [{ name: 'gothic', count: 2 }, { name: 'romance', count: 1 }], moods: [{ name: 'atmospheric', count: 1 }], tropes: [],
  content_warnings: [{ name: 'violence', count: 1 }], pacing: [], year_min: 1900, year_max: 2020,
}
