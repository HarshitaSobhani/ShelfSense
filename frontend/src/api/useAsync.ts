import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './client'

export interface AsyncState<T> {
  data: T | undefined
  error: ApiError | null
  loading: boolean
  reload: () => void
}

interface Settled<T> {
  id: string
  data?: T
  error?: ApiError
}

/** Runs `fn` whenever `key` changes or `reload()` is called. Stale responses are ignored.
 *  `data` keeps the previous value while a new request is in flight. */
export function useAsync<T>(fn: () => Promise<T>, key: string): AsyncState<T> {
  const [tick, setTick] = useState(0)
  const [res, setRes] = useState<Settled<T>>()
  const fnRef = useRef(fn)
  useEffect(() => {
    fnRef.current = fn
  })
  const id = `${key}#${tick}`

  useEffect(() => {
    let live = true
    fnRef.current().then(
      (data) => live && setRes({ id, data }),
      (e: unknown) => live && setRes({ id, error: e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e)) }),
    )
    return () => {
      live = false
    }
  }, [id])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const settled = res?.id === id
  return { data: res?.data, error: settled ? (res.error ?? null) : null, loading: !settled, reload }
}
