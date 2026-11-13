import type { ReactNode } from 'react'
import { useState } from 'react'
import { useParams } from 'react-router'

import type { Property, Report } from '../api/types.ts'
import { useApiData } from '../api/useApiData.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextField } from '../components/TextField.tsx'
import { formatDay } from '../format.ts'
import { formatMoney } from '../money.ts'
import { canSeeDirectory, findMembership } from '../organizations/organizations.ts'
import { ApprovalFigures } from '../reports/ApprovalFigures.tsx'
import { Figure, Figures } from '../reports/Figure.tsx'
import {
  formatHours,
  formatTotals,
  humanize,
  periodQuery,
  REPEAT_ISSUES_SHOWN,
} from '../reports/reports.ts'
import type { Period } from '../reports/reports.ts'
import { NotFoundPage } from './NotFoundPage.tsx'

const EXPORTS = [
  { file: 'work-orders', label: 'Work orders' },
  { file: 'requests', label: 'Requests' },
  { file: 'estimates', label: 'Estimates' },
]

export function ReportsPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)

  if (!membership || !canSeeDirectory(membership.roles)) {
    return <NotFoundPage />
  }

  return <ReportView organizationId={membership.organization_id} />
}

function ReportView({ organizationId }: { organizationId: string }) {
  const [period, setPeriod] = useState<Period>({ from: '', to: '', propertyId: '' })
  const base = `/organizations/${organizationId}`
  const { data: properties } = useApiData<Property[]>(`${base}/properties`)
  const {
    data: report,
    error,
    loading,
  } = useApiData<Report>(`${base}/reports${periodQuery(period)}`)

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold">Reports</h1>

      <form
        aria-label="Report period"
        onSubmit={(event) => event.preventDefault()}
        className="grid gap-3 sm:grid-cols-3"
      >
        <TextField
          id="report-from"
          label="From"
          type="date"
          value={period.from}
          max={period.to || undefined}
          onChange={(from) => setPeriod({ ...period, from })}
        />
        <TextField
          id="report-to"
          label="To"
          type="date"
          value={period.to}
          min={period.from || undefined}
          onChange={(to) => setPeriod({ ...period, to })}
        />
        <SelectField
          id="report-property"
          label="Property"
          placeholder="All properties"
          value={period.propertyId ?? ''}
          options={(properties ?? []).map((item) => ({ value: item.id, label: item.name }))}
          onChange={(propertyId) => setPeriod({ ...period, propertyId })}
        />
      </form>

      <FormError message={error} />
      {loading && (
        <p role="status" className="text-slate-600">
          Loading report…
        </p>
      )}
      {report && (
        <>
          <p className="text-slate-600">
            Showing {formatDay(report.period_start)} to {formatDay(report.period_end)}. Dates are
            whole days in UTC.
          </p>
          <ReportSections report={report} />
        </>
      )}

      <section aria-labelledby="exports-heading" className="space-y-2">
        <h2 id="exports-heading" className="text-xl font-semibold">
          Export
        </h2>
        <p className="text-sm text-slate-600">
          Spreadsheet files for the period and property above. They hold references, places,
          statuses, dates and amounts, but no names of residents, no descriptions and no notes.
        </p>
        <ul className="flex flex-wrap gap-3">
          {EXPORTS.map((item) => (
            <li key={item.file}>
              <a
                className="inline-block rounded border border-slate-300 bg-white px-3 py-1 underline"
                href={`/api${base}/reports/export/${item.file}.csv${periodQuery(period)}`}
                download
              >
                Download {item.label.toLowerCase()} (CSV)
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = `report-${title.toLowerCase().replace(/[^a-z]+/g, '-')}`

  return (
    <section aria-labelledby={id} className="space-y-3">
      <h2 id={id} className="text-xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  )
}

function Counts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  if (entries.length === 0) return <p className="text-sm text-slate-600">None.</p>

  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
      {entries.map(([key, count]) => (
        <li key={key}>
          {humanize(key)}: <strong>{count}</strong>
        </li>
      ))}
    </ul>
  )
}

function DataTable({
  caption,
  headings,
  rows,
  empty,
}: {
  caption: string
  headings: string[]
  rows: ReactNode[][]
  empty: string
}) {
  if (rows.length === 0) return <p className="text-sm text-slate-600">{empty}</p>

  return (
    <div className="overflow-x-auto" role="group" aria-label={caption} tabIndex={0}>
      <table className="w-full min-w-max border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-slate-300">
            {headings.map((heading) => (
              <th key={heading} scope="col" className="px-2 py-1 font-semibold">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells, index) => (
            <tr key={index} className="border-b border-slate-100">
              {cells.map((cell, position) => (
                <td key={position} className="px-2 py-1">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ReportSections({ report }: { report: Report }) {
  const { requests, work_orders: orders, resolution, spend } = report

  return (
    <>
      <Section title="Requests">
        <Figures>
          <Figure label="Open requests" value={requests.open} />
          <Figure label="Waiting for triage" value={requests.waiting_for_triage} />
          <Figure label="Submitted in period" value={requests.submitted_in_period} />
        </Figures>
        <Counts counts={requests.by_status} />
      </Section>

      <Section title="Work orders">
        <Figures>
          <Figure label="Open work orders" value={orders.open} />
          <Figure label="Overdue" value={orders.overdue} />
          <Figure label="Blocked" value={orders.blocked} />
          <Figure label="Created in period" value={orders.created_in_period} />
        </Figures>
        <Counts counts={orders.by_status} />
        <DataTable
          caption="Work orders created in the period, by property"
          headings={['Property', 'Created']}
          rows={orders.created_by_property.map((item) => [item.property_name, item.count])}
          empty="No work orders were created in this period."
        />
      </Section>

      <Section title="Time to resolve">
        <Figures>
          <Figure label="Verified in period" value={resolution.completed} />
          <Figure label="Average" value={formatHours(resolution.average_hours)} />
          <Figure label="Slowest" value={formatHours(resolution.slowest_hours)} />
        </Figures>
        <DataTable
          caption="Time to resolve, by priority"
          headings={['Priority', 'Verified', 'Average']}
          rows={resolution.by_priority.map((item) => [
            humanize(item.priority),
            item.completed,
            formatHours(item.average_hours),
          ])}
          empty="No work was verified in this period."
        />
      </Section>

      <Section title="Contractor workload">
        <DataTable
          caption="Contractor workload"
          headings={[
            'Contractor',
            'Active',
            'Awaiting reply',
            'Overdue',
            'Finished',
            'Sent back',
            'Declined',
          ]}
          rows={report.contractors.map((item) => [
            item.name,
            item.active_jobs,
            item.awaiting_response,
            item.overdue,
            item.completed,
            item.sent_back,
            item.declined,
          ])}
          empty="No contractor has been given work."
        />
      </Section>

      <Section title="Repeat issues">
        <DataTable
          caption="The same problem reported again in the same place"
          headings={['Property', 'Unit', 'Category', 'Times', 'Work orders']}
          rows={report.repeat_issues.map((item) => [
            item.property_name,
            item.unit_label ?? 'Common areas',
            humanize(item.category),
            item.count,
            item.references.join(', '),
          ])}
          empty="Nothing was reported twice in the same place."
        />
        {report.repeat_issues.length >= REPEAT_ISSUES_SHOWN && (
          <p className="text-sm text-slate-600">
            Showing the {REPEAT_ISSUES_SHOWN} most repeated problems.
          </p>
        )}
      </Section>

      <Section title="Repair spend">
        <Figures>
          <Figure label="Verified work" value={spend.work_orders} />
          <Figure label="Total" value={formatTotals(spend.total)} />
        </Figures>
        <DataTable
          caption="Repair spend by property"
          headings={['Property', 'Work orders', 'Spend']}
          rows={spend.by_property.map((item) => [
            item.property_name,
            item.work_orders,
            formatMoney(item.total_cents, item.currency),
          ])}
          empty="No verified work had a cost in this period."
        />
        <DataTable
          caption="Repair spend by category"
          headings={['Category', 'Spend']}
          rows={spend.by_category.map((item) => [
            humanize(item.category),
            formatMoney(item.total_cents, item.currency),
          ])}
          empty="No verified work had a cost in this period."
        />
      </Section>

      <Section title="Approvals">
        <ApprovalFigures approvals={report.approvals} />
      </Section>
    </>
  )
}
