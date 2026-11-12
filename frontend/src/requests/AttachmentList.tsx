import type { Attachment } from '../api/types.ts'
import { formatSize } from './labels.ts'

type AttachmentListProps = {
  attachments: Attachment[]
  // Address of the file route for this request; the file's ID is added to it.
  baseUrl: string
}

export function AttachmentList({ attachments, baseUrl }: AttachmentListProps) {
  if (attachments.length === 0) {
    return <p className="text-sm text-slate-600">No photos or documents attached.</p>
  }

  return (
    <ul aria-label="Attachments" className="grid gap-3 sm:grid-cols-2">
      {attachments.map((attachment) => {
        const url = `/api${baseUrl}/${attachment.id}`
        const isImage = attachment.content_type.startsWith('image/')
        return (
          <li key={attachment.id} className="space-y-2 rounded border border-slate-200 bg-white p-3">
            {isImage && (
              <a href={url} target="_blank" rel="noreferrer">
                <img
                  src={url}
                  alt={attachment.filename}
                  loading="lazy"
                  className="max-h-48 w-full rounded object-cover"
                />
              </a>
            )}
            <p className="text-sm">
              <a href={url} target="_blank" rel="noreferrer" className="underline">
                {attachment.filename}
              </a>{' '}
              <span className="text-slate-500">({formatSize(attachment.size_bytes)})</span>
              {attachment.visibility === 'internal' && (
                <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                  Internal
                </span>
              )}
            </p>
          </li>
        )
      })}
    </ul>
  )
}
