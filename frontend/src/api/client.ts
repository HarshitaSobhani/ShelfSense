export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
  /** Field-level messages from a 422 response, keyed by field name. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {}
    if (this.code === 'validation_error' && Array.isArray(this.details)) {
      for (const d of this.details as { field: string; message: string }[]) out[d.field] = d.message
    }
    return out
  }
}

const BASE = '/api/v1'

function csrfToken(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)shelfsense_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

export type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>

export function qs(params?: Query): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)))
    else sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export async function api<T>(method: string, path: string, opts: { params?: Query; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') {
    const t = csrfToken()
    if (t) headers['X-CSRF-Token'] = t
  }
  let res: Response
  try {
    res = await fetch(`${BASE}${path}${qs(opts.params)}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Could not reach the server. Check your connection and try again.')
  }
  if (res.status === 204) return undefined as T
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const e = (data as { error?: { code: string; message: string; details?: unknown } } | null)?.error
    throw new ApiError(res.status, e?.code ?? 'http_error', e?.message ?? `Request failed (${res.status})`, e?.details)
  }
  return data as T
}

export const get = <T>(path: string, params?: Query) => api<T>('GET', path, { params })
export const post = <T>(path: string, body?: unknown) => api<T>('POST', path, { body: body ?? {} })
export const put = <T>(path: string, body: unknown, params?: Query) => api<T>('PUT', path, { body, params })
export const patch = <T>(path: string, body: unknown) => api<T>('PATCH', path, { body })
export const del = <T = void>(path: string) => api<T>('DELETE', path)
