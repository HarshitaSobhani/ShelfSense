import { describe, expect, it } from 'vitest'
import { ApiError, api, qs } from '../api/client'
import { calls, mockFetch } from './helpers'

describe('api client', () => {
  it('builds query strings, skipping empty values and repeating arrays', () => {
    expect(qs({ a: 1, b: '', c: undefined, d: ['x', 'y'], e: false })).toBe('?a=1&d=x&d=y&e=false')
    expect(qs()).toBe('')
  })

  it('sends the CSRF cookie as a header on mutations only', async () => {
    document.cookie = 'shelfsense_csrf=tok123; path=/'
    mockFetch(() => ({ json: {} }))
    await api('POST', '/library', { body: { book_id: 1 } })
    await api('GET', '/books')
    expect(calls[0].headers['X-CSRF-Token']).toBe('tok123')
    expect(calls[1].headers['X-CSRF-Token']).toBeUndefined()
  })

  it('turns error responses into ApiError with field details', async () => {
    mockFetch(() => ({ status: 422, json: { error: { code: 'validation_error', message: 'bad', details: [{ field: 'password', message: 'too short' }] } } }))
    const e = (await api('POST', '/auth/register', { body: {} }).catch((x: unknown) => x)) as ApiError
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(422)
    expect(e.fieldErrors()).toEqual({ password: 'too short' })
  })

  it('reports network failures with a friendly message', async () => {
    const { vi } = await import('vitest')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))
    await expect(api('GET', '/books')).rejects.toMatchObject({ code: 'network_error' })
  })

  it('returns undefined for 204', async () => {
    mockFetch(() => ({ status: 204 }))
    await expect(api('DELETE', '/library/1')).resolves.toBeUndefined()
  })
})
