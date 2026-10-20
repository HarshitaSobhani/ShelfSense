import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, del, get, put } from '../api/client'
import { STATUS_LABEL, type Entry, type Goal, type LibraryOut, type Status } from '../api/types'
import { useAsync } from '../api/useAsync'
import { Cover } from '../components/Cover'
import { EmptyState, ErrorState, GridSkeleton, Pagination, ProgressBar, Select } from '../components/ui'

function GoalCard() {
  const year = new Date().getFullYear()
  const goal = useAsync(() => get<Goal>('/goals', { year }), `goal-${year}`)
  const [val, setVal] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const n = Number(val)
    if (!Number.isInteger(n) || n < 1 || n > 1000) return setErr('Enter a whole number from 1 to 1000.')
    setErr(null)
    try {
      await put('/goals', { target_books: n }, { year })
      setVal('')
      goal.reload()
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : 'Could not save goal')
    }
  }
  const g = goal.data
  const pct = g?.target_books ? Math.min(100, Math.round((100 * g.completed) / g.target_books)) : 0
  return (
    <section aria-labelledby="goal-h" className="rounded-lg border border-rule bg-card p-5">
      <h2 id="goal-h" className="text-xl font-semibold">
        {year} reading goal
      </h2>
      {goal.error && <ErrorState error={goal.error} onRetry={goal.reload} />}
      {g && (
        <>
          {g.target_books ? (
            <div className="mt-2">
              <p className="text-sm text-ink-soft">
                {g.completed} of {g.target_books} books finished
              </p>
              <div className="mt-2">
                <ProgressBar value={pct} label="Goal progress" />
              </div>
            </div>
          ) : (
            <p className="mt-1 text-sm text-ink-soft">Set a target and finished books count toward it.</p>
          )}
          <form onSubmit={save} noValidate className="mt-3 flex items-end gap-2">
            <div className="w-32">
              <label htmlFor="goal" className="mb-1 block text-sm font-semibold">
                Books this year
              </label>
              <input id="goal" className="input" type="number" min={1} max={1000} value={val} onChange={(e) => setVal(e.target.value)} />
            </div>
            <button className="btn">{g.target_books ? 'Update' : 'Set goal'}</button>
          </form>
          {err && (
            <p role="alert" className="mt-1 text-sm text-alert">
              {err}
            </p>
          )}
        </>
      )}
    </section>
  )
}

function EntryRow({ e, onChange }: { e: Entry; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setErr(null)
    try {
      await fn()
      onChange()
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <li className="flex gap-4 rounded-lg border border-rule bg-card p-4">
      <div className="w-20 shrink-0">
        <Cover book={e.book} size="sm" />
      </div>
      <div className="min-w-0 flex-1">
        <Link to={`/books/${e.book.id}`} className="font-display text-lg font-semibold hover:text-forest hover:underline">
          {e.book.title}
        </Link>
        <p className="text-sm text-ink-soft">
          {e.book.authors.join(', ')}
          {e.rating ? ` · you rated ${e.rating}★` : ''}
        </p>
        {e.status !== 'want_to_read' && (
          <div className="mt-2 max-w-sm">
            <ProgressBar value={e.progress_percent} label={`Progress on ${e.book.title}`} />
            <p className="mt-1 text-xs text-ink-soft">
              {e.progress_percent}%{e.finished_at ? ` · finished ${e.finished_at}` : ''}
            </p>
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div className="w-40">
            <Select label="Status" value={e.status} disabled={busy} onChange={(ev) => act(() => put(`/library/${e.book.id}/status`, { status: ev.target.value }))}>
              {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </Select>
          </div>
          <button className="btn btn-danger" disabled={busy} onClick={() => act(() => del(`/library/${e.book.id}`))} aria-label={`Remove ${e.book.title} from shelf`}>
            Remove
          </button>
        </div>
        {err && (
          <p role="alert" className="mt-1 text-sm text-alert">
            {err}
          </p>
        )}
      </div>
    </li>
  )
}

export function Library() {
  const [status, setStatus] = useState<Status | ''>('')
  const [page, setPage] = useState(1)
  const lib = useAsync(() => get<LibraryOut>('/library', { status, page, page_size: 12 }), `lib-${status}-${page}`)
  const total = lib.data ? Object.values(lib.data.counts).reduce((a, b) => a + b, 0) : 0
  return (
    <div>
      <h1 className="text-3xl font-semibold sm:text-4xl">My shelf</h1>
      <div className="mt-6 grid gap-8 lg:grid-cols-[1fr_20rem]">
        <section aria-label="Books on your shelf">
          <div role="group" aria-label="Shelf filter" className="mb-5 flex flex-wrap gap-2">
            {([['', 'All'], ...Object.entries(STATUS_LABEL)] as [Status | '', string][]).map(([s, label]) => (
              <button
                key={s || 'all'}
                aria-pressed={status === s}
                className={`chip ${status === s ? 'chip-on' : ''}`}
                onClick={() => {
                  setStatus(s)
                  setPage(1)
                }}
              >
                {label}
                {lib.data && <span className="ml-1 opacity-70">{s ? lib.data.counts[s] : total}</span>}
              </button>
            ))}
          </div>
          {lib.loading && <GridSkeleton n={4} />}
          {lib.error && <ErrorState error={lib.error} onRetry={lib.reload} />}
          {lib.data && lib.data.items.length === 0 && (
            <EmptyState title={status ? `Nothing in “${STATUS_LABEL[status]}”` : 'Your shelf is empty'} action={<Link to="/discover" className="btn">Find a book</Link>}>
              Add books from Discover or a book page.
            </EmptyState>
          )}
          {lib.data && lib.data.items.length > 0 && (
            <ul className="space-y-3">
              {lib.data.items.map((e) => (
                <EntryRow key={e.id} e={e} onChange={lib.reload} />
              ))}
            </ul>
          )}
          {lib.data && <Pagination page={lib.data.meta.page} pages={lib.data.meta.pages} onPage={setPage} />}
        </section>
        <aside>
          <GoalCard />
        </aside>
      </div>
    </div>
  )
}
