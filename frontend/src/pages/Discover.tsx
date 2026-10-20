import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { get, type Query } from '../api/client'
import type { BrowseOut, Book, Facets, Factor, PageMeta, SearchMeta, SearchOut } from '../api/types'
import { useAsync } from '../api/useAsync'
import { BookCard } from '../components/BookCard'
import { EmptyState, ErrorState, GridSkeleton, Notice, Pagination, Select } from '../components/ui'

const MULTI = ['genre', 'mood', 'trope', 'avoid'] as const

interface Row { book: Book; explanation?: string; factors?: Factor[]; score?: number }
interface Normalized { rows: Row[]; meta: PageMeta; search: SearchMeta | null }

async function load(q: string, params: Query, mode: string, sort: string): Promise<Normalized> {
  if (q) {
    const r = await get<SearchOut>('/books/search', { ...params, q, mode })
    return { rows: r.items.map((i) => ({ book: i.book, explanation: i.explanation, factors: i.factors, score: i.score })), meta: r.meta, search: r.meta }
  }
  const r = await get<BrowseOut>('/books', { ...params, sort })
  return { rows: r.items.map((book) => ({ book })), meta: r.meta, search: null }
}

function FacetGroup({ title, k, items, selected, onToggle }: { title: string; k: string; items: { name: string; count: number }[]; selected: string[]; onToggle: (k: string, v: string) => void }) {
  return (
    <fieldset className="mb-5">
      <legend className="mb-2 text-sm font-semibold">{title}</legend>
      <div className="flex flex-wrap gap-1.5">
        {items.map((i) => (
          <button key={i.name} type="button" className="chip" aria-pressed={selected.includes(i.name)} onClick={() => onToggle(k, i.name)}>
            {i.name} <span className="ml-1 opacity-60">{i.count}</span>
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export function Discover() {
  const [sp, setSp] = useSearchParams()
  const [showFilters, setShowFilters] = useState(false)
  const q = sp.get('q') ?? ''
  const [draft, setDraft] = useState(q)
  const page = Number(sp.get('page') ?? '1') || 1
  const mode = sp.get('mode') ?? 'auto'
  const sort = sp.get('sort') ?? 'title'

  const params: Query = {
    genre: sp.getAll('genre'),
    mood: sp.getAll('mood'),
    trope: sp.getAll('trope'),
    avoid: sp.getAll('avoid'),
    pacing: sp.get('pacing'),
    year_min: sp.get('year_min'),
    year_max: sp.get('year_max'),
    page,
    page_size: 12,
  }
  const facets = useAsync(() => get<Facets>('/books/facets'), 'facets')
  const results = useAsync(() => load(q, params, mode, sort), sp.toString())

  const update = (mut: (n: URLSearchParams) => void) => {
    const n = new URLSearchParams(sp)
    mut(n)
    n.delete('page')
    setSp(n)
  }
  const toggle = (key: string, value: string) =>
    update((n) => {
      const cur = n.getAll(key)
      n.delete(key)
      ;(cur.includes(value) ? cur.filter((c) => c !== value) : [...cur, value]).forEach((v) => n.append(key, v))
    })
  const setOne = (key: string, value: string) => update((n) => (value ? n.set(key, value) : n.delete(key)))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setOne('q', draft.trim().length >= 2 ? draft.trim() : '')
  }
  const activeCount = MULTI.reduce((a, k) => a + sp.getAll(k).length, 0) + ['pacing', 'year_min', 'year_max'].filter((k) => sp.get(k)).length
  const clearAll = () => {
    setSp(q ? { q } : {})
  }

  const rows = results.data?.rows ?? []
  const meta = results.data?.meta
  const search = results.data?.search ?? null

  return (
    <div>
      <h1 className="text-3xl font-semibold sm:text-4xl">Discover</h1>
      <form onSubmit={submit} role="search" className="mt-5 flex flex-col gap-3 sm:flex-row">
        <label htmlFor="q" className="sr-only">
          Search books by meaning, mood or theme
        </label>
        <input
          id="q"
          className="input flex-1"
          placeholder="Describe what you want to read…"
          value={draft}
          maxLength={300}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button className="btn" type="submit">
          Search
        </button>
        {q && (
          <button
            type="button"
            className="btn btn-quiet"
            onClick={() => {
              setDraft('')
              setOne('q', '')
            }}
          >
            Clear search
          </button>
        )}
      </form>

      <div className="mt-6 grid gap-8 lg:grid-cols-[17rem_1fr]">
        <aside aria-label="Filters">
          <button
            className="btn btn-quiet mb-3 w-full lg:hidden"
            aria-expanded={showFilters}
            aria-controls="filters"
            onClick={() => setShowFilters((s) => !s)}
          >
            Filters{activeCount ? ` (${activeCount})` : ''}
          </button>
          <div id="filters" className={`${showFilters ? 'block' : 'hidden'} lg:block`}>
            {facets.loading && <p className="text-sm text-ink-soft">Loading filters…</p>}
            {facets.error && <ErrorState error={facets.error} onRetry={facets.reload} />}
            {facets.data && (
              <>
                <FacetGroup title="Genre" k="genre" items={facets.data.genres.slice(0, 16)} selected={sp.getAll('genre')} onToggle={toggle} />
                <FacetGroup title="Mood" k="mood" items={facets.data.moods.slice(0, 16)} selected={sp.getAll('mood')} onToggle={toggle} />
                <FacetGroup title="Tropes" k="trope" items={facets.data.tropes.slice(0, 16)} selected={sp.getAll('trope')} onToggle={toggle} />
                <FacetGroup title="Hide content warnings" k="avoid" items={facets.data.content_warnings} selected={sp.getAll('avoid')} onToggle={toggle} />
                <div className="mb-5 grid grid-cols-2 gap-3">
                  <Select label="Pacing" value={sp.get('pacing') ?? ''} onChange={(e) => setOne('pacing', e.target.value)}>
                    <option value="">Any</option>
                    <option value="slow">Slow</option>
                    <option value="medium">Medium</option>
                    <option value="fast">Fast</option>
                  </Select>
                  {!q && (
                    <Select label="Sort" value={sort} onChange={(e) => setOne('sort', e.target.value)}>
                      <option value="title">Title</option>
                      <option value="year_desc">Newest first</option>
                      <option value="year_asc">Oldest first</option>
                      <option value="recent">Recently added</option>
                    </Select>
                  )}
                  <div>
                    <label htmlFor="ymin" className="mb-1 block text-sm font-semibold">
                      From year
                    </label>
                    <input id="ymin" className="input" type="number" inputMode="numeric" value={sp.get('year_min') ?? ''} onChange={(e) => setOne('year_min', e.target.value)} />
                  </div>
                  <div>
                    <label htmlFor="ymax" className="mb-1 block text-sm font-semibold">
                      To year
                    </label>
                    <input id="ymax" className="input" type="number" inputMode="numeric" value={sp.get('year_max') ?? ''} onChange={(e) => setOne('year_max', e.target.value)} />
                  </div>
                </div>
                {q && (
                  <Select label="Search mode" value={mode} onChange={(e) => setOne('mode', e.target.value === 'auto' ? '' : e.target.value)}>
                    <option value="auto">Automatic (best available)</option>
                    <option value="hybrid">Semantic + keyword</option>
                    <option value="semantic">Semantic only</option>
                    <option value="keyword">Keyword only</option>
                  </Select>
                )}
                <button className="btn btn-quiet mt-4 w-full" onClick={clearAll} disabled={!activeCount}>
                  Clear filters
                </button>
              </>
            )}
          </div>
        </aside>

        <section aria-live="polite" aria-busy={results.loading}>
          {results.loading && <GridSkeleton />}
          {results.error && <ErrorState error={results.error} onRetry={results.reload} />}
          {!results.loading && !results.error && meta && (
            <>
              <p className="mb-4 text-sm text-ink-soft">
                {meta.total} {meta.total === 1 ? 'book' : 'books'}
                {search && ` for “${q}” · ${search.mode_used} search`}
              </p>
              {search?.notice && (
                <div className="mb-4">
                  <Notice tone="warn">{search.notice}</Notice>
                </div>
              )}
              {search && search.books_without_embeddings > 0 && (
                <div className="mb-4">
                  <Notice>{search.books_without_embeddings} books have no embedding yet and are ranked by keywords only.</Notice>
                </div>
              )}
              {rows.length === 0 ? (
                <EmptyState
                  title="No books match"
                  action={
                    <button className="btn" onClick={() => { setDraft(''); setSp({}) }}>
                      Reset search and filters
                    </button>
                  }
                >
                  Try fewer filters or describe the book differently.
                </EmptyState>
              ) : (
                <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 xl:grid-cols-4">
                  {rows.map((r) => (
                    <BookCard key={r.book.id} book={r.book} explanation={r.explanation} factors={r.factors} score={r.score} />
                  ))}
                </div>
              )}
              <Pagination
                page={meta.page}
                pages={meta.pages}
                onPage={(p) => {
                  const n = new URLSearchParams(sp)
                  n.set('page', String(p))
                  setSp(n)
                  window.scrollTo?.({ top: 0 })
                }}
              />
            </>
          )}
        </section>
      </div>
    </div>
  )
}
