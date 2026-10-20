import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { calls, mockFetch, renderApp, USER } from './helpers'

describe('auth pages', () => {
  it('validates the login form before calling the API', async () => {
    mockFetch(() => undefined)
    renderApp('/login')
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/auth/login')).toBe(false)
  })

  it('signs in and redirects, then shows the signed-in nav', async () => {
    mockFetch(({ path }) => (path === '/auth/login' ? { json: { user: USER, csrf_token: 't' } } : path === '/books/facets' ? { json: { genres: [], moods: [], tropes: [], content_warnings: [], pacing: [], year_min: null, year_max: null } } : path === '/books' ? { json: { items: [], meta: { page: 1, page_size: 12, total: 0, pages: 1 } } } : undefined))
    renderApp('/login')
    await userEvent.type(await screen.findByLabelText('Email'), 'reader@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Discover' })).toBeInTheDocument()
    expect(calls.find((c) => c.path === '/auth/login')?.body).toEqual({ email: 'reader@example.com', password: 'correct horse battery' })
    expect(screen.getAllByText('Reader').length).toBeGreaterThan(0)
  })

  it('shows the server error for bad credentials', async () => {
    mockFetch(({ path }) => (path === '/auth/login' ? { status: 401, json: { error: { code: 'invalid_credentials', message: 'Incorrect email or password' } } } : undefined))
    renderApp('/login')
    await userEvent.type(await screen.findByLabelText('Email'), 'a@b.co')
    await userEvent.type(screen.getByLabelText('Password'), 'nope')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password')
  })

  it('validates registration and maps server field errors', async () => {
    mockFetch(({ path }) => (path === '/auth/register' ? { status: 409, json: { error: { code: 'email_taken', message: 'An account with this email already exists' } } } : undefined))
    renderApp('/register')
    await userEvent.click(await screen.findByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Use at least 10 characters.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Display name'), 'Ann')
    await userEvent.type(screen.getByLabelText('Email'), 'ann@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'long enough password')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('An account with this email already exists')).toBeInTheDocument()
  })

  it('redirects protected pages to login when signed out', async () => {
    mockFetch(() => undefined)
    renderApp('/library')
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
  })

  it('signs out', async () => {
    mockFetch(({ path }) => (path === '/auth/logout' ? { status: 204 } : path === '/books' ? { json: { items: [], meta: { page: 1, page_size: 4, total: 0, pages: 1 } } } : undefined), USER)
    renderApp('/')
    const btn = await screen.findByRole('button', { name: 'Sign out' })
    await userEvent.click(btn)
    await waitFor(() => expect(screen.getByRole('link', { name: 'Sign in' })).toBeInTheDocument())
    expect(calls.some((c) => c.path === '/auth/logout' && c.method === 'POST')).toBe(true)
  })
})

describe('registration redirect', () => {
  it('lands on preferences after a successful registration', async () => {
    mockFetch(({ path }) => {
      if (path === '/auth/register') return { status: 201, json: { user: USER, csrf_token: 't' } }
      if (path === '/books/facets') return { json: { genres: [], moods: [], tropes: [], content_warnings: [], pacing: [], year_min: null, year_max: null } }
      if (path === '/me/preferences') return { json: { genres: [], moods: [], tropes: [], avoid_content_warnings: [], pacing: null } }
      return undefined
    })
    renderApp('/register')
    await userEvent.type(await screen.findByLabelText('Display name'), 'Ann')
    await userEvent.type(screen.getByLabelText('Email'), 'ann@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'long enough password')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('heading', { name: 'Reading preferences' })).toBeInTheDocument()
  })
})
