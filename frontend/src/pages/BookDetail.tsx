import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ApiError, del, get, patch, post, put } from '../api/client'
import { STATUS_LABEL, type Book, type MyBookState, type Note, type SearchOut, type Status } from '../api/types'
import { useAsync } from '../api/useAsync'
import { useAuth } from '../auth/AuthContext'
import { BookCard } from '../components/BookCard'
import { Cover } from '../components/Cover'
import { EmptyState, ErrorState, Notice, ProgressBar, Select, Spinner, Stars, TextArea } from '../components/ui'

function Tags({ label, items, param }: { label: string; items: string[]; param: string }) {
  if (!items.length) return null
  return (
    <div className="mt-3">
      <h3 className="mb-1 text-xs font-semibold tracking-wide text-ink-soft uppercase">{label}</h3>
      <div className="flex flex-wrap gap-1.5">
        {items.map((t) => (
          <Link key={t} className="chip hover:border-forest" to={`/discover?${param}=${encodeURIComponent(t)}`}>
            {t}
          </Link>
        ))}
      </div>
    </div>
  )
}

function Shelf({ book }: { book: Book }) {
  const state = useAsync(() => get<MyBookState>(`/me/books/${book.id}`), `state-${book.id}`)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [page, setPage] = useState('')
  const entry = state.data?.entry ?? null

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setErr(null)
    try {
      await fn()
      setMsg(ok)
      state.reload()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  if (state.loading && !state.data) return <Spinner label="Loading your shelf" />
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />
  return (
    <section aria-labelledby="shelf-h" className="rounded-lg border border-rule bg-card p-5">
      <h2 id="shelf-h" className="text-xl font-semibold">
        Your shelf
      </h2>
      <div aria-live="polite" className="min-h-5 text-sm">
        {err && <p role="alert" className="text-alert">{err}</p>}
        {!err && msg && <p className="text-forest">{msg}</p>}
      </div>
      {entry ? (
        <div className="space-y-4">
          <Select label="Status" value={entry.status} disabled={busy} onChange={(e) => run(() => put(`/library/${book.id}/status`, { status: e.target.value }), 'Status updated')}>
            {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </Select>
          <div>
            <ProgressBar value={entry.progress_percent} label="Reading progress" />
            <p className="mt-1 text-sm text-ink-soft">
              {book.page_count || entry.progress_percent > 0 ? `${entry.progress_percent}% read` : 'Progress not set'}
              {entry.current_page ? ` · page ${entry.current_page}` : ''}
              {book.page_count ? ` of ${book.page_count}` : ' (total pages unknown)'}
            </p>
          </div>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              const n = Number(page)
              if (!Number.isFinite(n) || n < 0) return setErr('Enter a valid page number')
              run(() => patch(`/library/${book.id}/progress`, { current_page: n }), 'Progress saved')
              setPage('')
            }}
          >
            <div className="w-28">
              <label htmlFor="pg" className="mb-1 block text-sm font-semibold">
                Current page
              </label>
              <input id="pg" className="input" type="number" min={0} max={book.page_count ?? undefined} value={page} onChange={(e) => setPage(e.target.value)} />
            </div>
            <button className="btn" disabled={busy || page === ''}>
              Save page
            </button>
          </form>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e: FormEvent<HTMLFormElement>) => {
              e.preventDefault()
              const v = Number(new FormData(e.currentTarget).get('pct'))
              run(() => patch(`/library/${book.id}/progress`, { progress_percent: v }), 'Progress saved')
            }}
          >
            <div className="w-28">
              <label htmlFor="pct" className="mb-1 block text-sm font-semibold">
                Percent read
              </label>
              <input id="pct" name="pct" className="input" type="number" min={0} max={100} defaultValue={entry.progress_percent} key={entry.progress_percent} />
            </div>
            <button className="btn btn-quiet" disabled={busy}>
              Save %
            </button>
          </form>
          <button className="btn btn-danger" disabled={busy} onClick={() => run(() => del(`/library/${book.id}`), 'Removed from your shelf')}>
            Remove from shelf
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-ink-soft">Add this book to a shelf to track it.</p>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
              <button key={s} className="btn btn-quiet" disabled={busy} onClick={() => run(() => post('/library', { book_id: book.id, status: s }), `Added as “${STATUS_LABEL[s]}”`)}>
                {STATUS_LABEL[s]}
              </button>
            ))}
          </div>
        </div>
      )}
      <hr className="rule my-5" />
      <h3 className="mb-1 text-sm font-semibold">Your rating</h3>
      <Stars
        value={state.data?.rating ?? null}
        disabled={busy}
        onChange={(v) => run(() => put(`/books/${book.id}/rating`, { value: v }), `Rated ${v} of 5`)}
      />
      {state.data?.rating != null && (
        <button className="btn btn-quiet mt-2" disabled={busy} onClick={() => run(() => del(`/books/${book.id}/rating`), 'Rating cleared')}>
          Clear rating
        </button>
      )}
    </section>
  )
}

function Notes({ bookId }: { bookId: number }) {
  const notes = useAsync(() => get<Note[]>(`/books/${bookId}/notes`), `notes-${bookId}`)
  const [body, setBody] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [editBody, setEditBody] = useState('')
  const [err, setErr] = useState<string | null>(null)

  const wrap = async (fn: () => Promise<unknown>) => {
    setErr(null)
    try {
      await fn()
      notes.reload()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not save note')
    }
  }
  return (
    <section aria-labelledby="notes-h" className="rounded-lg border border-rule bg-card p-5">
      <h2 id="notes-h" className="text-xl font-semibold">
        Private notes
      </h2>
      <p className="text-sm text-ink-soft">Only you can see these.</p>
      <form
        className="mt-3 space-y-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (!body.trim()) return setErr('Write something first.')
          wrap(() => post(`/books/${bookId}/notes`, { body })).then(() => setBody(''))
        }}
      >
        <TextArea label="New note" value={body} maxLength={5000} onChange={(e) => setBody(e.target.value)} error={err ?? undefined} />
        <button className="btn">Add note</button>
      </form>
      {notes.loading && !notes.data && <Spinner label="Loading notes" />}
      {notes.error && <ErrorState error={notes.error} onRetry={notes.reload} />}
      <ul className="mt-4 space-y-3">
        {notes.data?.map((n) => (
          <li key={n.id} className="rounded border border-rule bg-paper p-3">
            {editing === n.id ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  wrap(() => put(`/notes/${n.id}`, { body: editBody })).then(() => setEditing(null))
                }}
                className="space-y-2"
              >
                <TextArea label="Edit note" value={editBody} onChange={(e) => setEditBody(e.target.value)} />
                <div className="flex gap-2">
                  <button className="btn">Save</button>
                  <button type="button" className="btn btn-quiet" onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <>
                <p className="whitespace-pre-wrap">{n.body}</p>
                <p className="mt-1 text-xs text-ink-soft">{new Date(n.updated_at).toLocaleString()}</p>
                <div className="mt-2 flex gap-2">
                  <button className="btn btn-quiet" onClick={() => { setEditing(n.id); setEditBody(n.body) }}>
                    Edit
                  </button>
                  <button className="btn btn-danger" onClick={() => wrap(() => del(`/notes/${n.id}`))}>
                    Delete
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      {notes.data?.length === 0 && <p className="mt-3 text-sm text-ink-soft">No notes yet.</p>}
    </section>
  )
}

export function BookDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const loc = useLocation()
  const book = useAsync(() => get<Book>(`/books/${id}`), `book-${id}`)
  const similar = useAsync(() => get<SearchOut>(`/books/${id}/similar`, { limit: 6 }), `similar-${id}`)
  useEffect(() => {
    if (book.data) document.title = `${book.data.title} · ShelfSense`
    return () => {
      document.title = 'ShelfSense: find books by meaning'
    }
  }, [book.data])

  if (book.loading) return <Spinner label="Loading book" />
  if (book.error)
    return book.error.status === 404 ? (
      <EmptyState title="Book not found" action={<Link to="/discover" className="btn">Back to Discover</Link>}>
        It may have been removed.
      </EmptyState>
    ) : (
      <ErrorState error={book.error} onRetry={book.reload} />
    )
  const b = book.data!
  return (
    <div>
      <Link to="/discover" className="text-sm font-semibold text-forest hover:underline">
        ← Discover
      </Link>
      <div className="mt-4 grid gap-8 md:grid-cols-[14rem_1fr] lg:grid-cols-[16rem_1fr_20rem]">
        <div className="mx-auto w-48 md:w-full">
          <Cover book={b} size="lg" />
        </div>
        <div>
          <h1 className="text-3xl leading-tight font-semibold sm:text-4xl">{b.title}</h1>
          {b.subtitle && <p className="mt-1 text-lg text-ink-soft">{b.subtitle}</p>}
          <p className="mt-2 text-ink-soft">
            by <span className="font-semibold text-ink">{b.authors.join(', ') || 'unknown author'}</span>
            {b.first_publish_year ? ` · first published ${b.first_publish_year}` : ''}
            {b.page_count ? ` · ${b.page_count} pages` : ''}
            {b.pacing ? ` · ${b.pacing} pacing` : ''}
          </p>
          {b.description ? (
            <p className="mt-5 max-w-prose text-lg leading-relaxed">{b.description}</p>
          ) : (
            <p className="mt-5 text-ink-soft italic">No description is available for this book yet.</p>
          )}
          <Tags label="Genres" items={b.genres} param="genre" />
          <Tags label="Mood" items={b.moods} param="mood" />
          <Tags label="Tropes" items={b.tropes} param="trope" />
          {b.content_warnings.length > 0 && (
            <div className="mt-3">
              <h3 className="mb-1 text-xs font-semibold tracking-wide text-ember uppercase">Content notes</h3>
              <p className="text-sm">{b.content_warnings.join(', ')}</p>
              <p className="text-xs text-ink-soft">Editorial annotations; not exhaustive.</p>
            </div>
          )}
          {b.has_embedding === false && (
            <div className="mt-4">
              <Notice>This book has no embedding yet, so similar-book suggestions use shared tags only.</Notice>
            </div>
          )}
        </div>
        <div className="space-y-5 md:col-span-2 lg:col-span-1">
          {user ? (
            <>
              <Shelf book={b} />
              <Notes bookId={b.id} />
            </>
          ) : (
            <EmptyState
              title="Track this book"
              action={
                <Link to="/login" state={{ from: loc.pathname }} className="btn">
                  Sign in to use your shelf
                </Link>
              }
            >
              Save it, rate it and keep private notes.
            </EmptyState>
          )}
        </div>
      </div>

      <section className="mt-12" aria-labelledby="sim-h">
        <h2 id="sim-h" className="text-2xl font-semibold">
          Readers of this might also like
        </h2>
        {similar.loading && <Spinner label="Finding similar books" />}
        {similar.error && <ErrorState error={similar.error} onRetry={similar.reload} />}
        {similar.data && (
          <>
            {similar.data.meta.notice && (
              <div className="mt-3">
                <Notice tone="warn">{similar.data.meta.notice}</Notice>
              </div>
            )}
            {similar.data.items.length === 0 ? (
              <p className="mt-3 text-ink-soft">No similar books found in the catalog.</p>
            ) : (
              <div className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-6">
                {similar.data.items.map((r) => (
                  <BookCard key={r.book.id} book={r.book} explanation={r.explanation} factors={r.factors} score={r.score} />
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
