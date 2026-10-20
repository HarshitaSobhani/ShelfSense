import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ADMIN, book, calls, facets, meta, mockFetch, renderApp, searchMeta, USER } from './helpers'

const health = (active: boolean) => ({ status: 'ok', database: true, vector_backend: 'pgvector', semantic_search: { active, model: 'm', model_loaded: active, reason: active ? null : 'model not downloaded', setup: active ? null : 'Run python -m app.cli download-model', indexed_books: active ? 62 : 0, total_books: 62, stale_embeddings: 0 } })

describe('For you', () => {
  it('shows a cold-start empty state with next steps', async () => {
    mockFetch(({ path }) => (path === '/recommendations' ? { json: { items: [], meta: searchMeta({ cold_start: true, mode_used: 'cold_start', notice: 'Rate or save a few books, or set preferences, to get recommendations.' }) } } : undefined), USER)
    renderApp('/for-you')
    expect(await screen.findByText('We need a little taste to go on')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Set preferences' })).toHaveAttribute('href', '/settings')
  })

  it('toggles exclude-read and explains results', async () => {
    mockFetch(({ path }) => (path === '/recommendations' ? { json: { items: [{ book: book(), score: 0.5, explanation: 'Ranked because: shares atmospheric (mood)', factors: [] }], meta: searchMeta({ mode_used: 'embedding+metadata' }) } } : undefined), USER)
    renderApp('/for-you')
    expect(await screen.findByText(/embedding\+metadata/)).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText(/Hide books I have already read/))
    await waitFor(() => expect(calls.at(-1)?.params.get('exclude_read')).toBe('false'))
  })
})

describe('Library', () => {
  const entry = { id: 1, book: book(), status: 'reading', progress_percent: 40, current_page: 160, started_at: '2026-01-01', finished_at: null, updated_at: '2026-01-02T00:00:00Z', rating: 5 }
  const lib = { items: [entry], meta: meta(), counts: { want_to_read: 0, reading: 1, completed: 0, on_hold: 0 } }

  it('lists entries, changes status, removes, and sets a goal', async () => {
    mockFetch(({ method, path }) => {
      if (path === '/library' && method === 'GET') return { json: lib }
      if (path === '/library/1/status') return { json: entry }
      if (path === '/library/1' && method === 'DELETE') return { status: 204 }
      if (path === '/goals' && method === 'GET') return { json: { year: 2026, target_books: null, completed: 0 } }
      if (path === '/goals' && method === 'PUT') return { json: { year: 2026, target_books: 12, completed: 0 } }
      return undefined
    }, USER)
    renderApp('/library')
    expect(await screen.findByRole('link', { name: 'Rebecca' })).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Progress on Rebecca' })).toHaveAttribute('aria-valuenow', '40')
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'completed')
    await waitFor(() => expect(calls.find((c) => c.path === '/library/1/status')?.body).toEqual({ status: 'completed' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove Rebecca from shelf' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/library/1')).toBe(true))
    await userEvent.type(screen.getByLabelText('Books this year'), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Set goal' }))
    expect(await screen.findByText('Enter a whole number from 1 to 1000.')).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Books this year'))
    await userEvent.type(screen.getByLabelText('Books this year'), '12')
    await userEvent.click(screen.getByRole('button', { name: 'Set goal' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT' && c.path === '/goals')?.body).toEqual({ target_books: 12 }))
  })

  it('shows an empty state per filter', async () => {
    mockFetch(({ path }) => (path === '/library' ? { json: { items: [], meta: meta({ total: 0 }), counts: { want_to_read: 0, reading: 0, completed: 0, on_hold: 0 } } } : path === '/goals' ? { json: { year: 2026, target_books: null, completed: 0 } } : undefined), USER)
    renderApp('/library')
    expect(await screen.findByText('Your shelf is empty')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^Completed/ }))
    expect(await screen.findByText('Nothing in “Completed”')).toBeInTheDocument()
  })
})

describe('Settings', () => {
  it('saves preferences', async () => {
    mockFetch(({ method, path, body }) => {
      if (path === '/books/facets') return { json: facets }
      if (path === '/me/preferences') return { json: method === 'PUT' ? body : { genres: [], moods: [], tropes: [], avoid_content_warnings: [], pacing: null } }
      return undefined
    }, USER)
    renderApp('/settings')
    await userEvent.click(await screen.findByRole('button', { name: 'gothic' }))
    await userEvent.click(screen.getByRole('button', { name: 'violence' }))
    await userEvent.click(screen.getByLabelText('Fast'))
    await userEvent.click(screen.getByRole('button', { name: 'Save preferences' }))
    expect(await screen.findByText('Preferences saved.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ genres: ['gothic'], moods: [], tropes: [], avoid_content_warnings: ['violence'], pacing: 'fast' })
  })
})

describe('Evaluation', () => {
  const run = { id: 1, created_at: '2026-10-01T00:00:00Z', k: 5, catalog_size: 62, embedding_model: null, judgments_version: 'v1', results: { k: 5, modes: { keyword: { mean: { recall: 0.5, precision: 0.3, mrr: 0.6, ndcg: 0.55 }, queries: [{ q: 'cozy', recall: 0.5, precision: 0.3, mrr: 1, ndcg: 0.5, top: ['Rebecca'], relevant: ['Rebecca'] }] } }, skipped_modes: [{ mode: 'semantic', reason: 'embedding model or vector index unavailable' }], unresolved_titles: [], query_count: 15, caveat: 'Small hand-written judgments.' } }

  it('reports inactive semantic search, skipped modes and the caveat; hides admin tools from non-admins', async () => {
    mockFetch(({ path }) => (path === '/health' ? { json: health(false) } : path === '/evaluation/runs' ? { json: { runs: [run], judgments: { version: 'v1', note: 'n', query_count: 15 } } } : undefined), USER)
    renderApp('/evaluation')
    expect(await screen.findByText(/Not active\. model not downloaded/)).toBeInTheDocument()
    expect(await screen.findByText(/Not evaluated: semantic/)).toBeInTheDocument()
    expect(screen.getByText('Small hand-written judgments.')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '0.550' })).toBeInTheDocument()
    expect(screen.queryByText('Administrator tools')).not.toBeInTheDocument()
  })

  it('lets administrators run an evaluation', async () => {
    mockFetch(({ method, path }) => {
      if (path === '/health') return { json: health(true) }
      if (path === '/evaluation/runs') return { json: { runs: [], judgments: { version: 'v1', note: 'n', query_count: 15 } } }
      if (path === '/evaluation/run' && method === 'POST') return { json: { modes: {} } }
      return undefined
    }, ADMIN)
    renderApp('/evaluation')
    expect(await screen.findByText('No evaluation has been run yet')).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Run evaluation' }))
    await waitFor(() => expect(calls.find((c) => c.path === '/evaluation/run')?.body).toEqual({ k: 5 }))
  })

  it('validates the import query for admins', async () => {
    mockFetch(({ path }) => (path === '/health' ? { json: health(true) } : path === '/evaluation/runs' ? { json: { runs: [], judgments: { version: 'v1', note: 'n', query_count: 15 } } } : undefined), ADMIN)
    renderApp('/evaluation')
    await userEvent.type(await screen.findByLabelText('Import from Open Library'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Import up to 10' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('at least 2 characters')
  })
})

describe('Layout', () => {
  it('opens and closes the mobile menu and navigates', async () => {
    mockFetch(({ path }) => (path === '/books' ? { json: { items: [], meta: meta({ total: 0 }) } } : undefined), USER)
    renderApp('/')
    const menu = await screen.findByRole('button', { name: 'Menu' })
    await userEvent.click(menu)
    const nav = screen.getByRole('navigation', { name: 'Mobile' })
    expect(nav).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('link', { name: 'My shelf' }).at(-1)!)
    expect(screen.queryByRole('navigation', { name: 'Mobile' })).not.toBeInTheDocument()
  })

  it('renders the landing page and example searches', async () => {
    mockFetch(({ path }) => (path === '/books' ? { json: { items: [book()], meta: meta({ total: 1 }) } } : undefined))
    renderApp('/')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Find the book that fits')
    expect(screen.getByRole('link', { name: 'a cozy adventure with found family' })).toHaveAttribute('href', expect.stringContaining('/discover?q='))
    expect(await screen.findByRole('link', { name: 'Rebecca' })).toBeInTheDocument()
  })

  it('shows 404 for unknown routes', async () => {
    mockFetch(() => undefined)
    renderApp('/nope')
    expect(await screen.findByText('Page not found')).toBeInTheDocument()
  })
})
