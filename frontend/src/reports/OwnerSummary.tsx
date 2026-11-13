import { useState } from 'react'

import type { OwnerSummary as OwnerSummaryData } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'
import { formatDay } from '../format.ts'
import { approvalsPath } from '../organizations/organizations.ts'
import { ApprovalFigures } from './ApprovalFigures.tsx'
import { periodQuery } from './reports.ts'

/** The owner's own approval activity for a period, with a file of it to keep. */
export function OwnerSummary({ organizationId }: { organizationId: string }) {
  const [open, setOpen] = useState(false)

  return (
    <section aria-labelledby="owner-summary-heading" className="space-y-3">
      <h2 id="owner-summary-heading" className="text-lg font-semibold">
        Summary and export
      </h2>
      {open ? (
        <SummaryPanel organizationId={organizationId} />
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded border border-slate-300 bg-white px-3 py-1"
        >
          Show my approval summary
        </button>
      )}
    </section>
  )
}

function SummaryPanel({ organizationId }: { organizationId: string }) {
  const [period, setPeriod] = useState({ from: '', to: '' })
  const base = approvalsPath(organizationId)
  const query = periodQuery(period)
  const { data, error, loading } = useApiData<OwnerSummaryData>(
    `/organizations/${organizationId}/my-approvals/summary${query}`,
  )

  return (
    <div className="space-y-4">
      <form
        aria-label="Summary period"
        onSubmit={(event) => event.preventDefault()}
        className="grid gap-3 sm:grid-cols-2"
      >
        <TextField
          id="summary-from"
          label="From"
          type="date"
          value={period.from}
          max={period.to || undefined}
          onChange={(from) => setPeriod({ ...period, from })}
        />
        <TextField
          id="summary-to"
          label="To"
          type="date"
          value={period.to}
          min={period.from || undefined}
          onChange={(to) => setPeriod({ ...period, to })}
        />
      </form>
      <FormError message={error} />
      {loading && (
        <p role="status" className="text-slate-600">
          Loading summary…
        </p>
      )}
      {data && (
        <>
          <p className="text-slate-600">
            Estimates from {formatDay(data.period_start)} to {formatDay(data.period_end)} at your
            properties.
          </p>
          <ApprovalFigures approvals={data.approvals} />
        </>
      )}
      <a
        className="inline-block rounded border border-slate-300 bg-white px-3 py-1 underline"
        href={`/api${base}/export.csv${query}`}
        download
      >
        Download approvals (CSV)
      </a>
    </div>
  )
}
