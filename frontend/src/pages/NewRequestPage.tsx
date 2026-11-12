import { useState, type SubmitEventHandler } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { api } from '../api/client.ts'
import type { MyHome, ResidentRequest, RequestCategory, Urgency } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useAction } from '../api/useAction.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'
import { TextField } from '../components/TextField.tsx'
import { findMembership, isResident, myRequestsPath } from '../organizations/organizations.ts'
import {
  ACCEPTED_FILE_TYPES,
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  describeFileProblem,
  MAX_FILES,
  URGENCY_LABELS,
  URGENCY_ORDER,
} from '../requests/labels.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

export function NewRequestPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !isResident(membership.roles)) {
    return <NotFoundPage />
  }

  return <NewRequestForm organizationId={membership.organization_id} />
}

function homeLabel(home: MyHome): string {
  return `${home.building_name ? `${home.building_name} · ` : ''}${home.unit_label}, ${home.property_name}`
}

function NewRequestForm({ organizationId }: { organizationId: string }) {
  const base = `/organizations/${organizationId}`
  const navigate = useNavigate()
  const homes = useApiData<MyHome[]>(`${base}/my-home`)
  const { busy, error, run, fail } = useAction()

  const [unitId, setUnitId] = useState('')
  const [category, setCategory] = useState<RequestCategory | ''>('')
  const [urgency, setUrgency] = useState<Urgency>('routine')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [location, setLocation] = useState('')
  const [accessNotes, setAccessNotes] = useState('')
  const [files, setFiles] = useState<File[]>([])

  const chosenUnit = unitId || homes.data?.[0]?.unit_id || ''
  const fileProblems = files.map(describeFileProblem).filter((problem) => problem !== null)

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (files.length > MAX_FILES) {
      fail(`Attach at most ${MAX_FILES} files.`)
      return
    }
    if (fileProblems.length > 0) {
      fail(fileProblems.join(' '))
      return
    }

    let created: ResidentRequest | null = null
    const failedUploads: string[] = []
    const submitted = await run(async () => {
      created = await api<ResidentRequest>(`${base}/my-requests`, {
        method: 'POST',
        body: {
          unit_id: chosenUnit,
          category,
          urgency,
          title,
          description,
          location,
          access_notes: accessNotes,
        },
      })
      // The report is saved first. A photo that fails afterwards must not lose it.
      for (const file of files) {
        try {
          await api(`${base}/my-requests/${created.id}/attachments`, {
            method: 'POST',
            file,
            query: { filename: file.name },
          })
        } catch {
          failedUploads.push(file.name)
        }
      }
    })

    if (submitted && created) {
      const target = (created as ResidentRequest).id
      navigate(`${myRequestsPath(organizationId)}/${target}`, {
        state: { submitted: true, failedUploads },
      })
    }
  }

  if (homes.loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading…
      </p>
    )
  }

  if (homes.error || !homes.data || homes.data.length === 0) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Report a problem</h1>
        <FormError message={homes.error} />
        <p className="text-slate-600">
          No home is linked to your account yet, so a request cannot be filed. Contact your property
          manager and ask them to add you to your unit.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to={myRequestsPath(organizationId)} className="text-sm text-slate-600 underline">
          My requests
        </Link>
        <h1 className="text-2xl font-semibold">Report a problem</h1>
      </div>

      <form
        onSubmit={handleSubmit}
        aria-label="Report a problem"
        className="space-y-4 rounded border border-slate-200 bg-white p-4"
      >
        <FormError message={error} />

        {homes.data.length > 1 ? (
          <SelectField
            id="request-home"
            label="Which home"
            value={chosenUnit}
            options={homes.data.map((home) => ({ value: home.unit_id, label: homeLabel(home) }))}
            onChange={setUnitId}
          />
        ) : (
          <p className="text-sm">
            <span className="font-medium">Home:</span> {homeLabel(homes.data[0])}
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            id="request-category"
            label="What kind of problem"
            required
            placeholder="Choose one"
            value={category}
            options={CATEGORY_ORDER.map((value) => ({ value, label: CATEGORY_LABELS[value] }))}
            onChange={(value) => setCategory(value as RequestCategory | '')}
          />
          <SelectField
            id="request-urgency"
            label="How urgent"
            value={urgency}
            options={URGENCY_ORDER.map((value) => ({ value, label: URGENCY_LABELS[value] }))}
            onChange={(value) => setUrgency(value as Urgency)}
          />
        </div>
        {urgency === 'emergency' && (
          <p role="note" className="rounded bg-amber-50 p-3 text-sm text-amber-900">
            If anyone is in danger, call your local emergency number first. Then submit this request
            so the property team knows.
          </p>
        )}

        <TextField
          id="request-title"
          label="Short summary"
          required
          minLength={3}
          maxLength={200}
          value={title}
          onChange={setTitle}
        />
        <TextAreaField
          id="request-description"
          label="What is happening"
          required
          maxLength={5000}
          value={description}
          onChange={setDescription}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id="request-location"
            label="Where in the home"
            maxLength={200}
            value={location}
            onChange={setLocation}
          />
          <TextField
            id="request-access"
            label="Access notes"
            maxLength={1000}
            placeholder="Pets, best times, who to call"
            value={accessNotes}
            onChange={setAccessNotes}
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="request-files" className="block text-sm font-medium text-slate-700">
            Photos or PDFs
          </label>
          <input
            id="request-files"
            type="file"
            multiple
            accept={ACCEPTED_FILE_TYPES.join(',')}
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            className="block text-sm"
          />
          {fileProblems.length > 0 && (
            <ul className="text-sm text-red-800">
              {fileProblems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
        </div>

        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {busy ? 'Sending…' : 'Send request'}
        </button>
      </form>
    </div>
  )
}
