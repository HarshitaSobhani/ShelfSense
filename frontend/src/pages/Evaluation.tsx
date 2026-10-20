import { useState } from 'react'
import { ApiError, get, post } from '../api/client'
import type { EvalRuns, Health } from '../api/types'
import { useAsync } from '../api/useAsync'
import { useAuth } from '../auth/AuthContext'
import { EmptyState, ErrorState, Notice, Spinner } from '../components/ui'

const f = (n: number) => n.toFixed(3)

function AdminTools({ onDone }: { onDone: () => void }) {
  const [k, setK] = useState(5)
  const [busy, setBusy] = useState<string | null>(null)
  const [out, setOut] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label)
    setErr(null)
    setOut(null)
    try {
      setOut(JSON.stringify(await fn(), null, 2).slice(0, 1500))
      onDone()
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.message}` : 'Failed')
    } finally {
      setBusy(null)
    }
  }
  return (
    <section aria-labelledby="admin-h" className="mt-10 rounded-lg border border-rule bg-card p-5">
      <h2 id="admin-h" className="text-xl font-semibold">
        Administrator tools
      </h2>
      <div className="mt-4 grid gap-6 md:grid-cols-3">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            run('eval', () => post('/evaluation/run', { k }))
          }}
        >
          <label htmlFor="k" className="mb-1 block text-sm font-semibold">
            Cutoff k
          </label>
          <input id="k" type="number" className="input" min={1} max={20} value={k} onChange={(e) => setK(Number(e.target.value))} />
          <button className="btn mt-2" disabled={!!busy}>
            {busy === 'eval' ? 'Running…' : 'Run evaluation'}
          </button>
        </form>
        <div>
          <p className="mb-1 text-sm font-semibold">Embedding index</p>
          <button className="btn btn-quiet" disabled={!!busy} onClick={() => run('rebuild', () => post('/admin/embeddings/rebuild', { force: false }))}>
            {busy === 'rebuild' ? 'Indexing…' : 'Index missing or changed books'}
          </button>
          <button className="btn btn-quiet mt-2" disabled={!!busy} onClick={() => run('rebuild-all', () => post('/admin/embeddings/rebuild', { force: true }))}>
            {busy === 'rebuild-all' ? 'Rebuilding…' : 'Force full rebuild'}
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (query.trim().length < 2) return setErr('Enter at least 2 characters to import.')
            run('import', () => post('/admin/import/openlibrary', { query: query.trim(), limit: 10 }))
          }}
        >
          <label htmlFor="ol" className="mb-1 block text-sm font-semibold">
            Import from Open Library
          </label>
          <input id="ol" className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="title or author" />
          <button className="btn mt-2" disabled={!!busy}>
            {busy === 'import' ? 'Importing…' : 'Import up to 10'}
          </button>
        </form>
      </div>
      {err && (
        <p role="alert" className="mt-4 text-sm text-alert">
          {err}
        </p>
      )}
      {out && (
        <pre className="mt-4 max-h-64 overflow-auto rounded bg-paper p-3 text-xs" aria-label="Result">
          {out}
        </pre>
      )}
    </section>
  )
}

export function Evaluation() {
  const { user } = useAuth()
  const health = useAsync(() => get<Health>('/health'), 'health')
  const runs = useAsync(() => (user ? get<EvalRuns>('/evaluation/runs') : Promise.reject(new ApiError(401, 'unauthorized', 'Sign in to view evaluation runs.'))), `runs-${user?.id ?? 0}`)
  const run = runs.data?.runs[0]
  const h = health.data?.semantic_search
  const refresh = () => {
    runs.reload()
    health.reload()
  }
  return (
    <div>
      <h1 className="text-3xl font-semibold sm:text-4xl">Search &amp; recommendation evaluation</h1>
      <p className="mt-2 max-w-3xl text-ink-soft">
        Metrics below are computed by executing the retrieval pipeline against a small set of hand-written relevance
        judgments. They are a regression check for this catalog, not a measure of real-world recommendation quality.
      </p>

      <section className="mt-6" aria-labelledby="status-h">
        <h2 id="status-h" className="text-xl font-semibold">
          Semantic search status
        </h2>
        {health.loading && <Spinner label="Checking" />}
        {health.error && <ErrorState error={health.error} onRetry={health.reload} />}
        {h && (
          <div className="mt-2 space-y-2">
            <Notice tone={h.active ? 'info' : 'warn'}>
              {h.active
                ? `Active: ${h.model} · ${h.indexed_books}/${h.total_books} books indexed (${health.data?.vector_backend}).`
                : `Not active. ${h.reason ?? 'No embeddings are indexed.'} Searches use keyword and tag matching only.`}
            </Notice>
            {!h.active && h.setup && <p className="text-sm text-ink-soft">{h.setup}</p>}
            {h.stale_embeddings > 0 && <Notice tone="warn">{h.stale_embeddings} embeddings were made with a different model or document format. Rebuild the index.</Notice>}
          </div>
        )}
      </section>

      <section className="mt-8" aria-labelledby="res-h">
        <h2 id="res-h" className="text-xl font-semibold">
          Latest run
        </h2>
        {runs.loading && <Spinner label="Loading runs" />}
        {runs.error && (runs.error.status === 401 ? <Notice>{runs.error.message}</Notice> : <ErrorState error={runs.error} onRetry={runs.reload} />)}
        {runs.data && !run && (
          <EmptyState title="No evaluation has been run yet">
            {user?.is_admin ? 'Use the administrator tools below to run one.' : 'An administrator needs to run one.'}
          </EmptyState>
        )}
        {run && (
          <div className="mt-3">
            <p className="text-sm text-ink-soft">
              {new Date(run.created_at).toLocaleString()} · k={run.k} · {run.catalog_size} books · {run.results.query_count} queries · embedding model: {run.embedding_model ?? 'none (keyword only)'} · judgments {run.judgments_version}
            </p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[32rem] border-collapse text-left text-sm">
                <caption className="sr-only">Mean retrieval metrics by search mode</caption>
                <thead>
                  <tr className="border-b border-rule">
                    <th scope="col" className="py-2">Mode</th>
                    <th scope="col">Recall@{run.k}</th>
                    <th scope="col">Precision@{run.k}</th>
                    <th scope="col">MRR</th>
                    <th scope="col">nDCG@{run.k}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(run.results.modes).map(([mode, r]) => (
                    <tr key={mode} className="border-b border-rule/60">
                      <th scope="row" className="py-2 capitalize">{mode}</th>
                      <td>{f(r.mean.recall)}</td>
                      <td>{f(r.mean.precision)}</td>
                      <td>{f(r.mean.mrr)}</td>
                      <td>{f(r.mean.ndcg)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {run.results.skipped_modes.length > 0 && (
              <div className="mt-3">
                <Notice tone="warn">
                  Not evaluated: {run.results.skipped_modes.map((s) => s.mode).join(', ')} ({run.results.skipped_modes[0].reason}).
                </Notice>
              </div>
            )}
            <p className="mt-3 text-xs text-ink-soft">{run.results.caveat}</p>
            {Object.entries(run.results.modes).map(([mode, r]) => (
              <details key={mode} className="mt-4">
                <summary className="cursor-pointer font-semibold">
                  Per-query results: <span className="capitalize">{mode}</span>
                </summary>
                <ul className="mt-2 space-y-2 text-sm">
                  {r.queries.map((q) => (
                    <li key={q.q} className="rounded border border-rule bg-card p-3">
                      <p className="font-semibold">“{q.q}”</p>
                      <p className="text-ink-soft">recall {f(q.recall)} · precision {f(q.precision)} · MRR {f(q.mrr)} · nDCG {f(q.ndcg)}</p>
                      <p>Top: {q.top.map((t) => (q.relevant.includes(t) ? `✓ ${t}` : t)).join(' · ') || 'no results'}</p>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        )}
      </section>
      {user?.is_admin && <AdminTools onDone={refresh} />}
    </div>
  )
}
