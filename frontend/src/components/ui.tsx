import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { ApiError } from '../api/client'

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 py-10 text-ink-soft">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-forest border-t-transparent" aria-hidden />
      <span>{label}…</span>
    </div>
  )
}

export function GridSkeleton({ n = 8 }: { n?: number }) {
  return (
    <div role="status" aria-label="Loading books" className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
      {Array.from({ length: n }, (_, i) => (
        <div key={i}>
          <div className="skeleton aspect-[2/3] w-full" />
          <div className="skeleton mt-3 h-4 w-3/4" />
          <div className="skeleton mt-2 h-3 w-1/2" />
        </div>
      ))}
    </div>
  )
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-rule bg-card/60 px-6 py-12 text-center">
      <h2 className="text-xl text-ink">{title}</h2>
      {children && <div className="mx-auto mt-2 max-w-md text-ink-soft">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-alert/40 bg-[#f8e9e6] px-5 py-4 text-alert">
      <p className="font-semibold">Something went wrong</p>
      <p className="mt-1 text-sm">{error.message}</p>
      {onRetry && (
        <button className="btn btn-danger mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warn' }) {
  const cls = tone === 'warn' ? 'border-ember/40 bg-[#f6eadb] text-ember' : 'border-forest/30 bg-forest-wash text-forest-dark'
  return (
    <div role="note" className={`rounded-lg border px-4 py-3 text-sm ${cls}`}>
      {children}
    </div>
  )
}

interface FieldProps {
  label: string
  error?: string
  hint?: string
}

export function Field({ label, error, hint, ...rest }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  const describedBy = [error ? `${id}-err` : '', hint ? `${id}-hint` : ''].filter(Boolean).join(' ') || undefined
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-semibold">
        {label}
      </label>
      <input id={id} className="input" aria-invalid={error ? true : undefined} aria-describedby={describedBy} {...rest} />
      {hint && !error && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-ink-soft">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} role="alert" className="mt-1 text-sm text-alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function TextArea({ label, error, ...rest }: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-semibold">
        {label}
      </label>
      <textarea id={id} className="input min-h-24" aria-invalid={error ? true : undefined} {...rest} />
      {error && (
        <p role="alert" className="mt-1 text-sm text-alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function Select({ label, children, ...rest }: { label: string } & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-semibold">
        {label}
      </label>
      <select id={id} className="input" {...rest}>
        {children}
      </select>
    </div>
  )
}

export function Pagination({ page, pages, onPage }: { page: number; pages: number; onPage: (p: number) => void }) {
  if (pages <= 1) return null
  return (
    <nav aria-label="Pagination" className="mt-8 flex items-center justify-center gap-3">
      <button className="btn btn-quiet" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Previous
      </button>
      <span className="text-sm text-ink-soft" aria-current="page">
        Page {page} of {pages}
      </span>
      <button className="btn btn-quiet" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next →
      </button>
    </nav>
  )
}

export function Stars({ value, onChange, disabled }: { value: number | null; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Your rating" className="flex gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} star${n > 1 ? 's' : ''}`}
          disabled={disabled}
          onClick={() => onChange(n)}
          className={`h-9 w-9 rounded text-2xl leading-none transition ${
            value !== null && n <= value ? 'text-ember' : 'text-rule hover:text-ember/60'
          } disabled:opacity-50`}
        >
          ★
        </button>
      ))}
    </div>
  )
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      className="h-2 w-full overflow-hidden rounded-full bg-paper-deep"
    >
      <div className="h-full bg-forest transition-all" style={{ width: `${value}%` }} />
    </div>
  )
}
