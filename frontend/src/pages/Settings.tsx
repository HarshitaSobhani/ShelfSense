import { useState } from 'react'
import { ApiError, get, put } from '../api/client'
import type { Facets, Preferences } from '../api/types'
import { useAsync } from '../api/useAsync'
import { useAuth } from '../auth/AuthContext'
import { ErrorState, Spinner } from '../components/ui'

type ListKey = 'genres' | 'moods' | 'tropes' | 'avoid_content_warnings'

function ChipPicker({ legend, options, selected, onToggle }: { legend: string; options: string[]; selected: string[]; onToggle: (v: string) => void }) {
  return (
    <fieldset className="mb-6">
      <legend className="mb-2 text-lg font-semibold">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <button key={o} type="button" className="chip" aria-pressed={selected.includes(o)} onClick={() => onToggle(o)}>
            {o}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export function Settings() {
  const { user } = useAuth()
  const facets = useAsync(() => get<Facets>('/books/facets'), 'facets-settings')
  const prefs = useAsync(() => get<Preferences>('/me/preferences'), 'prefs')
  const [edited, setP] = useState<Preferences | null>(null)
  const p = edited ?? prefs.data ?? null
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  if (prefs.loading || facets.loading) return <Spinner label="Loading preferences" />
  if (prefs.error) return <ErrorState error={prefs.error} onRetry={prefs.reload} />
  if (facets.error) return <ErrorState error={facets.error} onRetry={facets.reload} />
  if (!p || !facets.data) return null

  const toggle = (k: ListKey, v: string) => {
    setSaved(false)
    setP({ ...p, [k]: p[k].includes(v) ? p[k].filter((x) => x !== v) : [...p[k], v] })
  }
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    try {
      setP(await put<Preferences>('/me/preferences', p))
      setSaved(true)
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : 'Could not save preferences')
    }
  }
  return (
    <div className="max-w-3xl">
      <h1 className="text-3xl font-semibold sm:text-4xl">Reading preferences</h1>
      <p className="mt-2 text-ink-soft">
        Signed in as {user?.display_name} ({user?.email}). These shape your recommendations; they never leave your account.
      </p>
      <form onSubmit={save} className="mt-6">
        <ChipPicker legend="Genres you enjoy" options={facets.data.genres.map((g) => g.name)} selected={p.genres} onToggle={(v) => toggle('genres', v)} />
        <ChipPicker legend="Moods you look for" options={facets.data.moods.map((g) => g.name)} selected={p.moods} onToggle={(v) => toggle('moods', v)} />
        <ChipPicker legend="Tropes you love" options={facets.data.tropes.map((g) => g.name)} selected={p.tropes} onToggle={(v) => toggle('tropes', v)} />
        <ChipPicker
          legend="Content to avoid"
          options={facets.data.content_warnings.map((g) => g.name)}
          selected={p.avoid_content_warnings}
          onToggle={(v) => toggle('avoid_content_warnings', v)}
        />
        <fieldset className="mb-6">
          <legend className="mb-2 text-lg font-semibold">Preferred pacing</legend>
          <div className="flex flex-wrap gap-4">
            {[['', 'No preference'], ['slow', 'Slow'], ['medium', 'Medium'], ['fast', 'Fast']].map(([v, l]) => (
              <label key={v} className="flex items-center gap-2">
                <input type="radio" name="pacing" className="accent-[var(--color-forest)]" checked={(p.pacing ?? '') === v} onChange={() => { setSaved(false); setP({ ...p, pacing: v || null }) }} />
                {l}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="flex items-center gap-4">
          <button className="btn">Save preferences</button>
          <span role="status" className="text-sm text-forest">
            {saved && 'Preferences saved.'}
          </span>
          {err && (
            <span role="alert" className="text-sm text-alert">
              {err}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
