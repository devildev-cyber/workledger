import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'

export function MessageForm({ url, onSent }: { url: string; onSent: () => void }) {
  const [body, setBody] = useState('')
  const { busy, error, run } = useAction()

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const sent = await run(() => api(url, { method: 'POST', body: { body } }))
    if (sent) {
      setBody('')
      onSent()
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Send a message" className="space-y-2">
      <FormError message={error} />
      <TextAreaField
        id="resident-message"
        label="Add a message"
        required
        maxLength={2000}
        rows={3}
        value={body}
        onChange={setBody}
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        Send message
      </button>
    </form>
  )
}
