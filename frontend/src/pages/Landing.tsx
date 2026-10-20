import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { get } from '../api/client'
import type { BrowseOut } from '../api/types'
import { useAsync } from '../api/useAsync'
import { BookCard } from '../components/BookCard'
import { Cover } from '../components/Cover'

const EXAMPLES = [
  'a cozy adventure with found family',
  'haunted house with creeping dread',
  'enemies to lovers with witty banter',
  'bleak dystopia about surveillance',
]

export function Landing() {
  const [q, setQ] = useState('')
  const nav = useNavigate()
  const featured = useAsync(() => get<BrowseOut>('/books', { page_size: 4, sort: 'recent' }), 'featured')
  const go = (e: FormEvent) => {
    e.preventDefault()
    if (q.trim().length >= 2) nav(`/discover?q=${encodeURIComponent(q.trim())}`)
  }
  return (
    <div>
      <section className="grid items-center gap-10 py-6 md:grid-cols-[1.15fr_1fr] md:py-14">
        <div>
          <p className="text-sm font-semibold tracking-[0.18em] text-forest uppercase">Book discovery by meaning</p>
          <h1 className="mt-3 text-4xl leading-[1.05] font-semibold text-ink sm:text-6xl">
            Find the book that fits <em className="text-forest">how you want to feel.</em>
          </h1>
          <p className="mt-5 max-w-xl text-lg text-ink-soft">
            Describe a mood, a theme or a trope in your own words. ShelfSense matches it to books by what they are
            about, not just their genre shelf, and tells you exactly why each one was suggested.
          </p>
          <form onSubmit={go} role="search" className="mt-7 flex max-w-xl flex-col gap-3 sm:flex-row">
            <label htmlFor="hero-q" className="sr-only">
              Describe the book you want
            </label>
            <input
              id="hero-q"
              className="input flex-1"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="e.g. a lyrical retelling of a myth"
              minLength={2}
              maxLength={300}
            />
            <button className="btn" type="submit" disabled={q.trim().length < 2}>
              Search by meaning
            </button>
          </form>
          <div className="mt-4 flex flex-wrap gap-2" aria-label="Example searches">
            {EXAMPLES.map((ex) => (
              <Link key={ex} to={`/discover?q=${encodeURIComponent(ex)}`} className="chip hover:border-forest">
                {ex}
              </Link>
            ))}
          </div>
        </div>
        <div aria-hidden className="relative mx-auto grid w-full max-w-sm grid-cols-3 gap-3">
          {['Rebecca', 'Dune', 'Circe', 'Piranesi', 'Beloved', 'Gone Girl'].map((t, i) => (
            <div key={t} className={i % 2 ? 'translate-y-6' : ''}>
              <Cover book={{ title: t, authors: [], cover_url: null }} />
            </div>
          ))}
        </div>
      </section>

      <section className="mt-12 grid gap-8 border-y border-rule py-10 md:grid-cols-3">
        {[
          ['Search by meaning', 'Natural-language queries are embedded and matched against book descriptions and themes, with keyword and tag matching as a transparent fallback.'],
          ['Filter by feel', 'Combine genre, mood, trope and pacing, and hide books with content you would rather avoid.'],
          ['Know why', 'Every recommendation shows its ranking factors: similarity score, shared tags and your own ratings.'],
        ].map(([h, p]) => (
          <div key={h}>
            <h2 className="text-xl font-semibold">{h}</h2>
            <p className="mt-2 text-ink-soft">{p}</p>
          </div>
        ))}
      </section>

      <section className="mt-12" aria-labelledby="fresh">
        <div className="flex items-end justify-between">
          <h2 id="fresh" className="text-2xl font-semibold">
            Recently added
          </h2>
          <Link to="/discover" className="font-semibold text-forest hover:underline">
            Browse the catalog →
          </Link>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-5 sm:grid-cols-4">
          {featured.loading && <p className="col-span-full text-ink-soft">Loading…</p>}
          {featured.error && (
            <p className="col-span-full text-ink-soft" role="alert">
              The catalog could not be loaded right now.
            </p>
          )}
          {featured.data?.items.map((b) => <BookCard key={b.id} book={b} />)}
        </div>
      </section>
    </div>
  )
}
