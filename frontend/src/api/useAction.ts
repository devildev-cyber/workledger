import { useCallback, useState } from 'react'

import { errorMessage } from '../format.ts'

/** Runs a change against the API, tracking whether it is busy and what went wrong. */
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Resolves true when the action succeeded, so callers know whether to close a form. */
  const run = useCallback(async (action: () => Promise<unknown>): Promise<boolean> => {
    setError(null)
    setBusy(true)
    try {
      await action()
      return true
    } catch (caught) {
      setError(errorMessage(caught))
      return false
    } finally {
      setBusy(false)
    }
  }, [])

  const fail = useCallback((message: string) => setError(message), [])
  const clear = useCallback(() => setError(null), [])

  return { busy, error, run, fail, clear }
}
