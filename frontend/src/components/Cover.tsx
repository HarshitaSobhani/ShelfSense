import { useState } from 'react'
import type { Book } from '../api/types'

const PALETTES: [string, string, string][] = [
  ['#2f5d46', '#e8efe2', '#c9a96a'],
  ['#5b3a29', '#f3e6d3', '#d1a35c'],
  ['#233a4d', '#e4ebf0', '#c8b27a'],
  ['#6b2f3a', '#f4e4e1', '#d7b58a'],
  ['#3d3a2a', '#efe9d4', '#b5a05a'],
  ['#2a4a4a', '#e2eeeb', '#d0b070'],
]

function hash(s: string): number {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i)
  return Math.abs(h)
}

export function Cover({ book, size = 'md' }: { book: Pick<Book, 'title' | 'authors' | 'cover_url'>; size?: 'sm' | 'md' | 'lg' }) {
  const [failed, setFailed] = useState(false)
  const [bg, fg, accent] = PALETTES[hash(book.title) % PALETTES.length]
  const dims = { sm: 'w-16', md: 'w-full', lg: 'w-full' }[size]
  const title = size === 'sm' ? 'text-[0.62rem]' : size === 'lg' ? 'text-2xl' : 'text-lg'
  const author = size === 'sm' ? 'text-[0.5rem]' : size === 'lg' ? 'text-sm' : 'text-xs'
  const shadow = '0 1px 0 rgba(255,255,255,.4) inset, 0 8px 18px -8px rgba(31,42,36,.45), 3px 0 0 rgba(0,0,0,.12) inset'

  if (book.cover_url && !failed) {
    return (
      <img
        src={book.cover_url}
        alt={`Cover of ${book.title}`}
        loading="lazy"
        onError={() => setFailed(true)}
        className={`${dims} aspect-[2/3] rounded-[3px] object-cover`}
        style={{ boxShadow: shadow }}
      />
    )
  }
  return (
    <div
      role="img"
      aria-label={`Cover of ${book.title}${book.authors.length ? ` by ${book.authors.join(', ')}` : ''}`}
      data-testid="cover-fallback"
      className={`${dims} aspect-[2/3] rounded-[3px] flex flex-col justify-between p-[9%] overflow-hidden`}
      style={{ background: bg, color: fg, boxShadow: shadow }}
    >
      <div style={{ borderTop: `2px solid ${accent}`, width: '28%' }} />
      <div>
        <div className={`font-display font-semibold leading-tight break-words ${title}`}>{book.title}</div>
        {book.authors[0] && (
          <div className={`mt-2 uppercase tracking-[0.14em] opacity-80 ${author}`} style={{ color: accent }}>
            {book.authors.join(' · ')}
          </div>
        )}
      </div>
    </div>
  )
}
