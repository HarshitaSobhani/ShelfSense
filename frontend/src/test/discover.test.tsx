import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { book, calls, facets, meta, mockFetch, renderApp, searchMeta } from './helpers'

const base = (extra?: Parameters<typeof mockFetch>[0]) =>
  mockFetch((r) => {
    const x = extra?.(r)
    if (x) return x
    if (r.path === '/books/facets') return { json: facets }
    if (r.path === '/books') return { json: { items: [book(), book({ id: 2, title: 'Jane Eyre', authors: ['Charlotte Brontë'] })], meta: meta({ total: 2 }) } }
    return undefined
  })

describe('Discover', () => {
  it('browses the catalog with facets and book cards', async () => {
    base()
    renderApp('/discover')
    expect(await screen.findByRole('link', { name: 'Rebecca' })).toHaveAttribute('href', '/books/1')
    expect(screen.getByText('2 books')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /gothic/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('applies a facet filter and sends it to the API', async () => {
    base()
    renderApp('/discover')
    await userEvent.click(await screen.findByRole('button', { name: /gothic/ }))
    await waitFor(() => expect(calls.at(-1)?.params.getAll('genre')).toEqual(['gothic']))
    expect(screen.getByRole('button', { name: /gothic/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(calls.at(-1)?.params.getAll('genre')).toEqual([]))
  })

  it('runs a semantic search and shows ranking explanations', async () => {
    base(({ path }) =>
      path === '/books/search'
        ? { json: { items: [{ book: book(), score: 0.71, explanation: 'Ranked because: semantic similarity 0.71 to your query', factors: [{ factor: 'semantic', weight: 1, value: 0.71, contribution: 0.71, evidence: 'embedding cosine similarity 0.71' }] }], meta: searchMeta() } }
        : undefined,
    )
    renderApp('/discover')
    await userEvent.type(await screen.findByLabelText(/Search books by meaning/), 'haunted manor')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText(/hybrid search/)).toBeInTheDocument()
    expect(calls.at(-1)?.params.get('q')).toBe('haunted manor')
    await userEvent.click(screen.getByText('Why this?'))
    expect(screen.getByText(/semantic similarity 0.71 to your query/)).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('semantic')).toBeInTheDocument()
  })

  it('tells the user when semantic search is not active', async () => {
    base(({ path }) =>
      path === '/books/search'
        ? { json: { items: [], meta: searchMeta({ mode_used: 'keyword', semantic_available: false, total: 0, notice: 'Semantic search is not active (model missing). Showing keyword and metadata matches only.' }) } }
        : undefined,
    )
    renderApp('/discover?q=anything')
    expect(await screen.findByRole('note')).toHaveTextContent('Semantic search is not active')
    expect(screen.getByText('No books match')).toBeInTheDocument()
  })

  it('shows an error with retry', async () => {
    let fail = true
    base(({ path }) => {
      if (path === '/books' && fail) return { status: 500, json: { error: { code: 'internal_error', message: 'Internal server error' } } }
      return undefined
    })
    renderApp('/discover')
    const retry = await screen.findByRole('button', { name: 'Try again' })
    fail = false
    await userEvent.click(retry)
    expect(await screen.findByRole('link', { name: 'Rebecca' })).toBeInTheDocument()
  })

  it('toggles the mobile filter panel', async () => {
    base()
    renderApp('/discover')
    const toggle = await screen.findByRole('button', { name: /^Filters/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })

  it('paginates', async () => {
    base(({ path, params }) => (path === '/books' ? { json: { items: [book({ id: Number(params.get('page')) })], meta: meta({ total: 24, pages: 2, page: Number(params.get('page')) }) } } : undefined))
    renderApp('/discover')
    await userEvent.click(await screen.findByRole('button', { name: /Next/ }))
    await waitFor(() => expect(calls.at(-1)?.params.get('page')).toBe('2'))
  })
})
