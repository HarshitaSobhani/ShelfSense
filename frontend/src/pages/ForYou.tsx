import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../api/client'
import type { SearchOut } from '../api/types'
import { useAsync } from '../api/useAsync'
import { BookCard } from '../components/BookCard'
import { EmptyState, ErrorState, GridSkeleton, Notice, Pagination } from '../components/ui'

export function ForYou() {
  const [excludeRead, setExcludeRead] = useState(true)
  const [pacing, setPacing] = useState('')
  const [page, setPage] = useState(1)
  const recs = useAsync(
    () => get<SearchOut>('/recommendations', { exclude_read: excludeRead, pacing, page, page_size: 12 }),
    `recs-${excludeRead}-${pacing}-${page}`,
  )
  const m = recs.data?.meta
  return (
    <div>
      <h1 className="text-3xl font-semibold sm:text-4xl">Recommended for you</h1>
      <p className="mt-2 max-w-2xl text-ink-soft">
        Built from the books you rated or saved and the preferences you set. Open “Why this?” on any card to see the
        similarity score, shared tags and ranking factors.
      </p>
      <div className="mt-5 flex flex-wrap items-end gap-5">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--color-forest)]"
            checked={excludeRead}
            onChange={(e) => {
              setExcludeRead(e.target.checked)
              setPage(1)
            }}
          />
          Hide books I have already read or rated
        </label>
        <div>
          <label htmlFor="pace" className="mb-1 block text-sm font-semibold">
            Pacing
          </label>
          <select
            id="pace"
            className="input"
            value={pacing}
            onChange={(e) => {
              setPacing(e.target.value)
              setPage(1)
            }}
          >
            <option value="">Any</option>
            <option value="slow">Slow</option>
            <option value="medium">Medium</option>
            <option value="fast">Fast</option>
          </select>
        </div>
      </div>
      <div className="mt-6" aria-live="polite">
        {recs.loading && <GridSkeleton />}
        {recs.error && <ErrorState error={recs.error} onRetry={recs.reload} />}
        {m?.notice && !m.cold_start && (
          <div className="mb-4">
            <Notice tone="warn">{m.notice}</Notice>
          </div>
        )}
        {m && !recs.loading && (
          <p className="mb-4 text-sm text-ink-soft">
            Method: <strong>{m.mode_used.replaceAll('_', ' ')}</strong>
          </p>
        )}
        {recs.data && recs.data.items.length === 0 && (
          <EmptyState
            title={m?.cold_start ? 'We need a little taste to go on' : 'No recommendations match'}
            action={
              <div className="flex flex-wrap justify-center gap-3">
                <Link to="/settings" className="btn">
                  Set preferences
                </Link>
                <Link to="/discover" className="btn btn-quiet">
                  Rate or save books
                </Link>
              </div>
            }
          >
            {m?.cold_start ? m.notice : 'Try relaxing the pacing filter or showing books you have read.'}
          </EmptyState>
        )}
        {recs.data && recs.data.items.length > 0 && (
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 xl:grid-cols-4">
            {recs.data.items.map((r) => (
              <BookCard key={r.book.id} book={r.book} explanation={r.explanation} factors={r.factors} score={r.score} />
            ))}
          </div>
        )}
        {m && <Pagination page={m.page} pages={m.pages} onPage={setPage} />}
      </div>
    </div>
  )
}
