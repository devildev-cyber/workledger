import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type { ApprovalMetrics, Membership, OwnerSummary, Report } from './api/types.ts'
import { formatHours, formatTotals, humanize, periodQuery } from './reports/reports.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asResident: Membership = { ...harborAdmin, roles: ['resident'] }
const asOwner: Membership = { ...harborAdmin, roles: ['property_owner'] }

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const approvals: ApprovalMetrics = {
  estimates_recorded: 3,
  needed_approval: 2,
  pending: 1,
  approved: 1,
  rejected: 0,
  replaced: 0,
  pending_amounts: [{ currency: 'USD', total_cents: 145_000 }],
  approved_amounts: [{ currency: 'USD', total_cents: 132_000 }],
  rejected_amounts: [],
  average_decision_hours: 5.5,
  by_property: [],
}

const report: Report = {
  period_start: '2026-08-16',
  period_end: '2026-11-13',
  requests: {
    open: 8,
    waiting_for_triage: 5,
    submitted_in_period: 10,
    by_status: { submitted: 4, in_review: 1 },
  },
  work_orders: {
    by_status: { on_hold: 1, closed: 1 },
    open: 3,
    overdue: 1,
    blocked: 2,
    created_in_period: 5,
    created_by_category: { plumbing: 2 },
    created_by_property: [{ property_id: 'p-1', property_name: 'Maple Court', count: 2 }],
  },
  resolution: {
    completed: 2,
    average_hours: 20,
    slowest_hours: 100,
    by_priority: [{ priority: 'urgent', completed: 1, average_hours: 10 }],
  },
  contractors: [
    {
      contractor_id: 'c-1',
      name: 'Casey Contractor',
      active_jobs: 2,
      awaiting_response: 1,
      overdue: 1,
      completed: 1,
      sent_back: 0,
      declined: 0,
    },
  ],
  repeat_issues: [
    {
      property_id: 'p-1',
      property_name: 'Maple Court',
      unit_label: null,
      category: 'plumbing',
      count: 3,
      references: ['WO-0001', 'WO-0004', 'WO-0007'],
    },
  ],
  spend: {
    work_orders: 2,
    total: [
      { currency: 'EUR', total_cents: 4_500 },
      { currency: 'USD', total_cents: 18_500 },
    ],
    by_property: [
      {
        property_id: 'p-1',
        property_name: 'Maple Court',
        currency: 'USD',
        total_cents: 18_500,
        work_orders: 1,
      },
    ],
    by_category: [{ category: 'heating', currency: 'USD', total_cents: 18_500 }],
  },
  approvals,
}

const PROPERTIES = [
  {
    id: 'p-1',
    name: 'Maple Court',
    street: '1 Maple',
    city: 'Portland',
    region: 'OR',
    postal_code: '97201',
    currency: 'USD',
    approval_threshold_cents: 50_000,
    unit_count: 10,
    buildings: [],
    managers: [],
  },
]

function plan(extra: Record<string, unknown> = {}) {
  return mockApi({
    'GET /api/auth/me': { body: sessionFor([asManager]) },
    [`GET ${ORG}/properties`]: { body: PROPERTIES },
    [`GET ${ORG}/reports`]: { body: report },
    ...Object.fromEntries(Object.entries(extra).map(([key, body]) => [key, { body }])),
  })
}

describe('the reports page', () => {
  it('shows every metric with the period it covers', async () => {
    plan()

    renderAt(`${ORG_PATH}/reports`)

    expect(await screen.findByRole('heading', { name: 'Reports' })).toBeInTheDocument()
    expect(await screen.findByText(/Showing .*2026.* to .*2026/)).toBeInTheDocument()
    const requests = screen.getByRole('region', { name: 'Requests' })
    expect(
      within(requests).getByText('Open requests', { selector: 'dt' }).nextSibling,
    ).toHaveTextContent('8')
    expect(
      within(requests).getByText('Waiting for triage', { selector: 'dt' }).nextSibling,
    ).toHaveTextContent('5')
    expect(within(requests).getByText(/In review:/)).toHaveTextContent('In review: 1')

    const orders = screen.getByRole('region', { name: 'Work orders' })
    expect(within(orders).getByText('Overdue', { selector: 'dt' }).nextSibling).toHaveTextContent(
      '1',
    )
    expect(within(orders).getByText('Blocked', { selector: 'dt' }).nextSibling).toHaveTextContent(
      '2',
    )

    const time = screen.getByRole('region', { name: 'Time to resolve' })
    expect(within(time).getByText('Average', { selector: 'dt' }).nextSibling).toHaveTextContent(
      '20 h',
    )
    expect(within(time).getByText('Slowest', { selector: 'dt' }).nextSibling).toHaveTextContent(
      '4.2 days',
    )

    const workload = screen.getByRole('table', { name: 'Contractor workload' })
    expect(within(workload).getByRole('cell', { name: 'Casey Contractor' })).toBeInTheDocument()

    const repeats = screen.getByRole('table', {
      name: 'The same problem reported again in the same place',
    })
    expect(within(repeats).getByText('Common areas')).toBeInTheDocument()
    expect(within(repeats).getByText('WO-0001, WO-0004, WO-0007')).toBeInTheDocument()

    const approvalsRegion = screen.getByRole('region', { name: 'Approvals' })
    expect(
      within(approvalsRegion).getByText('Waiting amount', { selector: 'dt' }).nextSibling,
    ).toHaveTextContent('$1,450.00')
  })

  it('shows each currency on its own and never adds them together', async () => {
    plan()

    renderAt(`${ORG_PATH}/reports`)

    const spend = await screen.findByRole('region', { name: 'Repair spend' })
    const total = within(spend).getByText('Total', { selector: 'dt' }).nextSibling as HTMLElement
    expect(total).toHaveTextContent('€45.00')
    expect(total).toHaveTextContent('$185.00')
    expect(total).not.toHaveTextContent('$230.00')
  })

  it('asks again for the chosen period and property', async () => {
    const { requests } = plan({
      [`GET ${ORG}/reports?from=2026-01-01&to=2026-01-31`]: report,
      [`GET ${ORG}/reports?from=2026-01-01&to=2026-01-31&property_id=p-1`]: report,
    })
    renderAt(`${ORG_PATH}/reports`)
    await screen.findByRole('region', { name: 'Requests' })

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-01-31' } })
    await waitFor(() =>
      expect(requests.map((item) => item.path)).toContain(
        `${ORG}/reports?from=2026-01-01&to=2026-01-31`,
      ),
    )
    fireEvent.change(screen.getByLabelText('Property'), { target: { value: 'p-1' } })

    await waitFor(() =>
      expect(requests.map((item) => item.path)).toContain(
        `${ORG}/reports?from=2026-01-01&to=2026-01-31&property_id=p-1`,
      ),
    )
  })

  it('offers the exports for the same period and property', async () => {
    plan({
      [`GET ${ORG}/reports?from=2026-01-01`]: report,
      [`GET ${ORG}/reports?from=2026-01-01&property_id=p-1`]: report,
    })
    renderAt(`${ORG_PATH}/reports`)
    await screen.findByRole('region', { name: 'Requests' })

    expect(screen.getByRole('link', { name: 'Download work orders (CSV)' })).toHaveAttribute(
      'href',
      `${ORG}/reports/export/work-orders.csv`,
    )

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })
    fireEvent.change(screen.getByLabelText('Property'), { target: { value: 'p-1' } })

    expect(screen.getByRole('link', { name: 'Download estimates (CSV)' })).toHaveAttribute(
      'href',
      `${ORG}/reports/export/estimates.csv?from=2026-01-01&property_id=p-1`,
    )
    expect(screen.getByRole('link', { name: 'Download requests (CSV)' })).toHaveAttribute(
      'href',
      `${ORG}/reports/export/requests.csv?from=2026-01-01&property_id=p-1`,
    )
  })

  it('explains an empty period instead of showing blank tables', async () => {
    plan({
      [`GET ${ORG}/reports`]: {
        ...report,
        contractors: [],
        repeat_issues: [],
        resolution: { completed: 0, average_hours: null, slowest_hours: null, by_priority: [] },
        spend: { work_orders: 0, total: [], by_property: [], by_category: [] },
      },
    })

    renderAt(`${ORG_PATH}/reports`)

    expect(await screen.findByText('No contractor has been given work.')).toBeInTheDocument()
    expect(screen.getByText('Nothing was reported twice in the same place.')).toBeInTheDocument()
    expect(screen.getByText('No work was verified in this period.')).toBeInTheDocument()
    expect(screen.getAllByText('No verified work had a cost in this period.')).toHaveLength(2)
  })

  it('shows why a report could not be loaded', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: PROPERTIES },
      [`GET ${ORG}/reports`]: {
        status: 422,
        body: { detail: 'Choose a period of ten years or less' },
      },
    })

    renderAt(`${ORG_PATH}/reports`)

    expect(await screen.findByRole('alert')).toHaveTextContent('ten years or less')
  })

  it('is in the menu for staff only', async () => {
    plan()
    renderAt(`${ORG_PATH}/reports`)
    expect(await screen.findByRole('link', { name: 'Reports' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/reports`,
    )
  })

  it('is not found for a resident, who has no link either', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests`]: { body: [] },
    })

    renderAt(`${ORG_PATH}/reports`)

    expect(await screen.findByText(/not found/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Reports' })).not.toBeInTheDocument()
  })
})

describe('the owner summary', () => {
  const summary: OwnerSummary = {
    period_start: '2026-08-16',
    period_end: '2026-11-13',
    approvals,
  }

  function owner(extra: Record<string, unknown> = {}) {
    return mockApi({
      'GET /api/auth/me': { body: sessionFor([asOwner]) },
      [`GET ${ORG}/my-approvals`]: { body: [] },
      ...Object.fromEntries(Object.entries(extra).map(([key, body]) => [key, { body }])),
    })
  }

  it('stays out of the way until asked for', async () => {
    const { requests } = owner()

    renderAt(`${ORG_PATH}/my-approvals`)

    expect(await screen.findByRole('button', { name: 'Show my approval summary' })).toBeVisible()
    expect(requests.some((item) => item.path.includes('summary'))).toBe(false)
  })

  it('shows the owner their decisions and a file to keep', async () => {
    owner({ [`GET ${ORG}/my-approvals/summary`]: summary })
    renderAt(`${ORG_PATH}/my-approvals`)

    fireEvent.click(await screen.findByRole('button', { name: 'Show my approval summary' }))

    expect(await screen.findByText('Approved amount')).toBeInTheDocument()
    expect(screen.getByText('Approved amount', { selector: 'dt' }).nextSibling).toHaveTextContent(
      '$1,320.00',
    )
    expect(
      screen.getByText('Average decision time', { selector: 'dt' }).nextSibling,
    ).toHaveTextContent('5.5 h')
    expect(screen.getByRole('link', { name: 'Download approvals (CSV)' })).toHaveAttribute(
      'href',
      `${ORG}/my-approvals/export.csv`,
    )
  })

  it('asks for the chosen period', async () => {
    const { requests } = owner({
      [`GET ${ORG}/my-approvals/summary`]: summary,
      [`GET ${ORG}/my-approvals/summary?from=2026-01-01`]: summary,
    })
    renderAt(`${ORG_PATH}/my-approvals`)
    fireEvent.click(await screen.findByRole('button', { name: 'Show my approval summary' }))
    await screen.findByText('Approved amount')

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })

    await waitFor(() =>
      expect(requests.map((item) => item.path)).toContain(
        `${ORG}/my-approvals/summary?from=2026-01-01`,
      ),
    )
    expect(screen.getByRole('link', { name: 'Download approvals (CSV)' })).toHaveAttribute(
      'href',
      `${ORG}/my-approvals/export.csv?from=2026-01-01`,
    )
  })
})

describe('report formatting', () => {
  it('leaves blank dates out so the server chooses the default period', () => {
    expect(periodQuery({ from: '', to: '' })).toBe('')
    expect(periodQuery({ from: '2026-01-01', to: '', propertyId: '' })).toBe('?from=2026-01-01')
    expect(periodQuery({ from: '', to: '2026-02-01', propertyId: 'p-1' })).toBe(
      '?to=2026-02-01&property_id=p-1',
    )
  })

  it('reads hours as days once they pass two days', () => {
    expect(formatHours(null)).toBe('No data')
    expect(formatHours(0)).toBe('0 h')
    expect(formatHours(47.5)).toBe('47.5 h')
    expect(formatHours(72)).toBe('3 days')
  })

  it('names statuses and totals plainly', () => {
    expect(humanize('ready_for_review')).toBe('Ready for review')
    expect(formatTotals([])).toBe('None')
    expect(formatTotals([{ currency: 'USD', total_cents: 100 }])).toBe('$1.00')
  })
})
