import { useRef, useState, type SubmitEventHandler } from 'react'

import { api } from '../api/client.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { ACCEPTED_FILE_TYPES, describeFileProblem } from './labels.ts'

type UploadFormProps = {
  url: string
  // Staff choose whether the resident can see the file. Residents do not get the choice.
  canShare?: boolean
  // Wording and query for the sharing choice. Requests share with the resident by default.
  shareLabel?: string
  shareQuery?: (share: boolean) => Record<string, string>
  label?: string
  onUploaded: () => void
}

const SHARE_WITH_RESIDENT = (share: boolean) => ({ visibility: share ? 'resident' : 'internal' })

export function UploadForm({
  url,
  canShare = false,
  shareLabel = 'Visible to the resident',
  shareQuery = SHARE_WITH_RESIDENT,
  label = 'Add a photo or PDF',
  onUploaded,
}: UploadFormProps) {
  const input = useRef<HTMLInputElement>(null)
  const [share, setShare] = useState(false)
  const { busy, error, run, fail } = useAction()

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const file = input.current?.files?.[0]
    if (!file) {
      fail('Choose a file first.')
      return
    }
    const problem = describeFileProblem(file)
    if (problem) {
      fail(problem)
      return
    }

    const uploaded = await run(() =>
      api(url, {
        method: 'POST',
        file,
        query: { filename: file.name, ...(canShare ? shareQuery(share) : {}) },
      }),
    )
    if (uploaded) {
      if (input.current) input.current.value = ''
      onUploaded()
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Attach a file" className="space-y-2">
      <FormError message={error} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label htmlFor="attach-file" className="block text-sm font-medium text-slate-700">
            {label}
          </label>
          <input
            id="attach-file"
            ref={input}
            type="file"
            accept={ACCEPTED_FILE_TYPES.join(',')}
            className="block text-sm"
          />
        </div>
        {canShare && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
            {shareLabel}
          </label>
        )}
        <button
          type="submit"
          disabled={busy}
          className="rounded border border-slate-300 px-3 py-2 text-sm disabled:opacity-60"
        >
          Upload
        </button>
      </div>
    </form>
  )
}
