import { formatSize } from '../requests/labels.ts'

type FileItem = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
}

type FileListProps = {
  files: FileItem[]
  // Address of the file route; each file's ID is added to it.
  baseUrl: string
  note?: (file: FileItem) => string | null
}

export function FileList({ files, baseUrl, note }: FileListProps) {
  if (files.length === 0) {
    return <p className="text-sm text-slate-600">No photos or documents yet.</p>
  }

  return (
    <ul aria-label="Files" className="grid gap-3 sm:grid-cols-2">
      {files.map((file) => {
        const url = `/api${baseUrl}/${file.id}`
        const detail = note?.(file)
        return (
          <li key={file.id} className="space-y-2 rounded border border-slate-200 bg-white p-3">
            {file.content_type.startsWith('image/') && (
              <a href={url} target="_blank" rel="noreferrer">
                <img
                  src={url}
                  alt={file.filename}
                  loading="lazy"
                  className="max-h-48 w-full rounded object-cover"
                />
              </a>
            )}
            <p className="text-sm">
              <a href={url} target="_blank" rel="noreferrer" className="underline">
                {file.filename}
              </a>{' '}
              <span className="text-slate-500">({formatSize(file.size_bytes)})</span>
              {detail && (
                <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                  {detail}
                </span>
              )}
            </p>
          </li>
        )
      })}
    </ul>
  )
}
