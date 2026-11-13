import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'

export function NoteForm({ url, onSaved }: { url: string; onSaved: () => void }) {
  const [body, setBody] = useState('')
  const [visibility, setVisibility] = useState<'internal' | 'resident'>('internal')
  const { busy, error, run, fail } = useAction()

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (body.trim() === '') {
      fail('Write the note first.')
      return
    }
    const saved = await run(() => api(url, { method: 'POST', body: { body, visibility } }))
    if (saved) {
      setBody('')
      onSaved()
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Add note"
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      <TextAreaField
        id="work-order-note"
        label="Note"
        maxLength={2000}
        rows={3}
        value={body}
        onChange={setBody}
      />
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium text-slate-700">Who can read it</legend>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="note-visibility"
            checked={visibility === 'internal'}
            onChange={() => setVisibility('internal')}
          />
          Internal note, staff only
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="note-visibility"
            checked={visibility === 'resident'}
            onChange={() => setVisibility('resident')}
          />
          Share with the residents of linked requests
        </label>
      </fieldset>
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        Add note
      </button>
    </form>
  )
}
