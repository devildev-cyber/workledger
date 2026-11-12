import { useState } from 'react'

import { api } from '../api/client.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'

export function WithdrawControl({ url, onWithdrawn }: { url: string; onWithdrawn: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const { busy, error, run } = useAction()

  const withdraw = async () => {
    if (await run(() => api(url, { method: 'POST' }))) {
      onWithdrawn()
    }
  }

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="rounded border border-slate-300 px-3 py-2 text-sm"
      >
        Withdraw request
      </button>
    )
  }

  return (
    <div role="group" aria-label="Confirm withdrawal" className="space-y-2">
      <FormError message={error} />
      <p className="text-sm">Withdraw this request? Nobody will work on it.</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={withdraw}
          disabled={busy}
          className="rounded bg-red-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          Yes, withdraw
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        >
          Keep request
        </button>
      </div>
    </div>
  )
}
