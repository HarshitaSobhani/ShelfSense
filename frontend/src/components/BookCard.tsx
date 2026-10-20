import { Link } from 'react-router-dom'
import type { Book, Factor } from '../api/types'
import { Cover } from './Cover'

export function BookCard({
  book,
  explanation,
  factors,
  score,
}: {
  book: Book
  explanation?: string
  factors?: Factor[]
  score?: number
}) {
  return (
    <article className="group flex flex-col">
      <Link to={`/books/${book.id}`} aria-label={`${book.title}, details`} className="block transition group-hover:-translate-y-0.5">
        <Cover book={book} />
      </Link>
      <div className="mt-3 flex-1">
        <h3 className="text-base leading-snug font-semibold">
          <Link to={`/books/${book.id}`} className="hover:text-forest hover:underline">
            {book.title}
          </Link>
        </h3>
        <p className="text-sm text-ink-soft">
          {book.authors.join(', ') || 'Unknown author'}
          {book.first_publish_year ? ` · ${book.first_publish_year}` : ''}
        </p>
        <div className="mt-2 flex flex-wrap gap-1">
          {[...book.genres.slice(0, 2), ...book.moods.slice(0, 1)].map((t) => (
            <span key={t} className="chip">
              {t}
            </span>
          ))}
        </div>
        {explanation && (
          <details className="mt-2 text-xs text-ink-soft">
            <summary className="cursor-pointer font-semibold text-forest">Why this?</summary>
            <p className="mt-1">{explanation}</p>
            {score !== undefined && <p className="mt-1">Score {score.toFixed(3)}</p>}
            {factors && factors.length > 0 && (
              <table className="mt-1 w-full text-left">
                <caption className="sr-only">Ranking factors</caption>
                <thead>
                  <tr>
                    <th scope="col">Factor</th>
                    <th scope="col">Value</th>
                    <th scope="col">Adds</th>
                  </tr>
                </thead>
                <tbody>
                  {factors.map((f) => (
                    <tr key={f.factor} title={f.evidence}>
                      <td>{f.factor}</td>
                      <td>{f.value.toFixed(2)}</td>
                      <td>{f.contribution.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </details>
        )}
      </div>
    </article>
  )
}
