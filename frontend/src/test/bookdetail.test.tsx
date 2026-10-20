import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { book, calls, mockFetch, renderApp, searchMeta, USER } from './helpers'

const empty = { json: { items: [], meta: searchMeta({ mode_used: 'embedding' }) } }

describe('BookDetail', () => {
  it('renders metadata and a graceful fallback for a missing description', async () => {
    mockFetch(({ path }) => (path === '/books/1' ? { json: book({ description: null, page_count: null }) } : path === '/books/1/similar' ? empty : undefined))
    renderApp('/books/1')
    expect(await screen.findByRole('heading', { name: 'Rebecca' })).toBeInTheDocument()
    expect(screen.getByText(/No description is available/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'gothic' })).toHaveAttribute('href', '/discover?genre=gothic')
    expect(screen.getByRole('link', { name: /Sign in to use your shelf/ })).toBeInTheDocument()
  })

  it('shows content notes and a not-found state', async () => {
    mockFetch(({ path }) => (path === '/books/1' ? { json: book({ content_warnings: ['violence'] }) } : path === '/books/1/similar' ? empty : undefined))
    const { unmount } = renderApp('/books/1')
    expect(await screen.findByText('violence')).toBeInTheDocument()
    unmount()
    mockFetch(() => undefined)
    renderApp('/books/999')
    expect(await screen.findByText('Book not found')).toBeInTheDocument()
  })

  it('adds a book to the shelf, rates it, and saves a note', async () => {
    let entry: unknown = null
    let rating: number | null = null
    mockFetch(({ method, path, body }) => {
      if (path === '/books/1') return { json: book() }
      if (path === '/books/1/similar') return empty
      if (path === '/me/books/1') return { json: { entry, rating } }
      if (path === '/library' && method === 'POST') {
        entry = { id: 1, book: book(), status: (body as { status: string }).status, progress_percent: 0, current_page: null, started_at: null, finished_at: null, updated_at: '2026-01-01T00:00:00Z', rating: null }
        return { status: 201, json: entry }
      }
      if (path === '/books/1/rating' && method === 'PUT') {
        rating = (body as { value: number }).value
        return { json: { book_id: 1, value: rating } }
      }
      if (path === '/books/1/notes') return method === 'POST' ? { status: 201, json: { id: 1 } } : { json: [] }
      return undefined
    }, USER)
    renderApp('/books/1')
    await userEvent.click(await screen.findByRole('button', { name: 'Want to read' }))
    expect(await screen.findByLabelText('Status')).toHaveValue('want_to_read')
    expect(calls.find((c) => c.path === '/library')?.body).toEqual({ book_id: 1, status: 'want_to_read' })
    await userEvent.click(screen.getByRole('radio', { name: '4 stars' }))
    await waitFor(() => expect(screen.getByRole('radio', { name: '4 stars' })).toHaveAttribute('aria-checked', 'true'))
    await userEvent.type(screen.getByLabelText('New note'), 'great opening')
    await userEvent.click(screen.getByRole('button', { name: 'Add note' }))
    await waitFor(() => expect(calls.find((c) => c.path === '/books/1/notes' && c.method === 'POST')?.body).toEqual({ body: 'great opening' }))
  })

  it('surfaces a duplicate-shelf error from the API', async () => {
    mockFetch(({ method, path }) => {
      if (path === '/books/1') return { json: book() }
      if (path === '/books/1/similar') return empty
      if (path === '/me/books/1') return { json: { entry: null, rating: null } }
      if (path === '/library' && method === 'POST') return { status: 409, json: { error: { code: 'already_in_library', message: 'This book is already on your shelf' } } }
      if (path === '/books/1/notes') return { json: [] }
      return undefined
    }, USER)
    renderApp('/books/1')
    await userEvent.click(await screen.findByRole('button', { name: 'Reading' }))
    expect(await screen.findByText('This book is already on your shelf')).toBeInTheDocument()
  })
})
