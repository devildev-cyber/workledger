import { useCallback, useEffect, useState } from 'react'

import { api, ApiError } from './client.ts'

type Result<T> = { path: string; version: number; data: T | null; error: string | null }

/**
 * Loads data from the API and lets the caller load it again after a change. While
 * reloading, the previous data stays available so lists do not flash empty.
 */
export function useApiData<T>(path: string) {
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState<Result<T> | null>(null)

  useEffect(() => {
    let cancelled = false

    api<T>(path)
      .then((data) => {
        if (!cancelled) setResult({ path, version, data, error: null })
      })
      .catch((caught: unknown) => {
        const error =
          caught instanceof ApiError ? caught.message : 'Something went wrong. Please try again.'
        if (!cancelled) setResult({ path, version, data: null, error })
      })

    return () => {
      cancelled = true
    }
  }, [path, version])

  const reload = useCallback(() => setVersion((current) => current + 1), [])

  // Ignore a result that belongs to a previous path, such as another organization.
  const current = result?.path === path ? result : null

  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: current === null,
    reload,
  }
}
