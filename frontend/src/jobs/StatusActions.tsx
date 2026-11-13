import { useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import type { WorkOrderStatus } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'
import { actionLabel, NOTE_PROMPTS } from './labels.ts'

type StatusActionsProps = {
  url: string
  current: WorkOrderStatus
  allowed: WorkOrderStatus[]
  onChanged: () => void
}

export function StatusActions({ url, current, allowed, onChanged }: StatusActionsProps) {
  // The move waiting for its explanation, when it needs one.
  const [asking, setAsking] = useState<WorkOrderStatus | null>(null)
  const [note, setNote] = useState('')
  const { busy, error, run, fail, clear } = useAction()

  if (allowed.length === 0) return null

  const move = async (status: WorkOrderStatus, text: string | null) => {
    const saved = await run(() => api(url, { method: 'POST', body: { status, note: text } }))
    if (saved) {
      setAsking(null)
      setNote('')
      onChanged()
    }
  }

  const choose = (status: WorkOrderStatus) => {
    if (NOTE_PROMPTS[status]) {
      clear()
      setAsking(status)
      return
    }
    void move(status, null)
  }

  const confirm: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (asking === null) return
    if (note.trim() === '') {
      fail(NOTE_PROMPTS[asking]?.label ?? 'Add a note first.')
      return
    }
    await move(asking, note)
  }

  const prompt = asking ? NOTE_PROMPTS[asking] : undefined

  return (
    <section aria-labelledby="actions-heading" className="space-y-3">
      <h2 id="actions-heading" className="text-xl font-semibold">
        Update the job
      </h2>
      {asking && prompt ? (
        <form
          onSubmit={confirm}
          aria-label={prompt.confirm}
          className="space-y-3 rounded border border-slate-200 bg-white p-4"
        >
          <FormError message={error} />
          <TextAreaField
            id="job-status-note"
            label={prompt.label}
            maxLength={1000}
            rows={3}
            value={note}
            onChange={setNote}
          />
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="submit"
              disabled={busy}
              className="min-h-12 rounded bg-slate-900 px-4 py-3 font-medium text-white disabled:opacity-60"
            >
              {prompt.confirm}
            </button>
            <button
              type="button"
              onClick={() => setAsking(null)}
              className="min-h-12 rounded border border-slate-300 bg-white px-4 py-3"
            >
              Back
            </button>
          </div>
        </form>
      ) : (
        <>
          <FormError message={error} />
          <div className="flex flex-col gap-3 sm:flex-row">
            {allowed.map((status) => (
              <button
                key={status}
                type="button"
                disabled={busy}
                onClick={() => choose(status)}
                className="min-h-12 rounded bg-slate-900 px-4 py-3 font-medium text-white disabled:opacity-60"
              >
                {actionLabel(current, status)}
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
