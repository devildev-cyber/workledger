import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type { Approval, ApprovalSummary, Estimate, Membership, WorkOrder } from './api/types.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asOwner: Membership = { ...harborAdmin, roles: ['property_owner'] }

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// --- The manager's side -----------------------------------------------------------------

function estimate(overrides: Partial<Estimate> = {}): Estimate {
  return {
    id: 'e-1',
    version: 1,
    amount_cents: 80000,
    currency: 'USD',
    description: 'Replace the cartridge and both washers.',
    provider_name: 'Harbor Plumbing',
    status: 'pending',
    approval_required: true,
    threshold_cents: 50000,
    current: true,
    submitted_by_name: 'Mo Manager',
    submitted_at: '2026-11-10T10:00:00Z',
    decided_by_name: null,
    decided_at: null,
    decision_reason: null,
    ...overrides,
  }
}

function workOrder(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'w-1',
    reference: 'WO-0001',
    title: 'Replace kitchen tap',
    status: 'assigned',
    priority: 'soon',
    category: 'plumbing',
    property_id: 'p-1',
    property_name: 'Maple Court',
    unit_label: '1A',
    building_name: null,
    due_date: null,
    overdue: false,
    request_count: 0,
    assignee_id: 'c-1',
    assignee_name: 'Casey Carpenter',
    assignment_response: 'accepted',
    final_cost_cents: null,
    currency: null,
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    scope: 'Fit a new cartridge.',
    linked_requests: [],
    history: [],
    allowed_statuses: ['in_progress'],
    assignment: null,
    assignment_history: [],
    attachments: [],
    property_currency: 'USD',
    resolution: null,
    verified_by_name: null,
    verified_at: null,
    estimates: [],
    approval_threshold_cents: 50000,
    owner_names: ['Olive Owner'],
    approval_hold: null,
    can_record_estimate: true,
    cost_check: null,
    ...overrides,
  }
}

function openWorkOrder(order: WorkOrder, extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/auth/me': { body: sessionFor([asManager]) },
    [`GET ${ORG}/contractors`]: { body: [] },
    [`GET ${ORG}/work-orders/w-1`]: { body: order },
    ...extra,
  })
}

describe('estimates on a work order', () => {
  it('explains the threshold and records an estimate in exact cents', async () => {
    let current = workOrder()
    const { requests } = openWorkOrder(current, {
      [`GET ${ORG}/work-orders/w-1`]: () => ({ body: current }),
      [`POST ${ORG}/work-orders/w-1/estimates`]: () => {
        current = workOrder({
          status: 'awaiting_approval',
          approval_hold: 'This work is waiting for the property owner’s approval',
          allowed_statuses: [],
          estimates: [estimate()],
        })
        return { status: 201, body: current }
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Record an estimate' })
    expect(within(form).getByText(/above \$500\.00 needs a property owner/)).toBeInTheDocument()

    fireEvent.click(within(form).getByRole('button', { name: 'Record estimate' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('such as 850')

    fireEvent.change(within(form).getByLabelText('Amount (USD)'), { target: { value: '800.00' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Record estimate' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Describe what')
    expect(requests.some((request) => request.method === 'POST')).toBe(false)

    fireEvent.change(within(form).getByLabelText('What it covers'), {
      target: { value: 'Replace the cartridge and both washers.' },
    })
    fireEvent.change(within(form).getByLabelText('Quoted by (optional)'), {
      target: { value: 'Harbor Plumbing' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Record estimate' }))

    expect(await screen.findByText(/waiting for the property owner/)).toBeInTheDocument()
    expect(screen.getByText('Waiting for Olive Owner.')).toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      amount_cents: 80000,
      description: 'Replace the cartridge and both washers.',
      provider_name: 'Harbor Plumbing',
    })
  })

  it('says so when nobody is able to approve', async () => {
    openWorkOrder(
      workOrder({
        status: 'awaiting_approval',
        approval_hold: 'This work is waiting for the property owner’s approval',
        owner_names: [],
        estimates: [estimate()],
      }),
    )

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(
      await screen.findByText(/No property owner is set for this property/),
    ).toBeInTheDocument()
  })

  it('shows every estimate with the decision on it, and a revision form', async () => {
    openWorkOrder(
      workOrder({
        status: 'on_hold',
        approval_hold: 'The property owner did not approve this work. Ask the property team',
        estimates: [
          estimate({
            id: 'e-1',
            status: 'rejected',
            decided_by_name: 'Olive Owner',
            decided_at: '2026-11-11T10:00:00Z',
            decision_reason: 'Too much',
          }),
        ],
      }),
    )

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    const list = await screen.findByRole('list', { name: 'Estimates' })
    expect(within(list).getByText(/\$800\.00/)).toBeInTheDocument()
    expect(within(list).getByText(/Rejected by Olive Owner/)).toHaveTextContent(': Too much')
    expect(screen.getByText(/Record a revised estimate to ask again/)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Revise the estimate' })).toBeInTheDocument()
  })

  it('offers no form once the work is finished', async () => {
    openWorkOrder(workOrder({ status: 'completed', can_record_estimate: false }))

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(await screen.findByText('No estimate has been recorded.')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Record an estimate' })).not.toBeInTheDocument()
  })

  it('warns when the final cost went over the estimate or the threshold', async () => {
    openWorkOrder(
      workOrder({
        status: 'completed',
        can_record_estimate: false,
        resolution: 'Replaced the cartridge.',
        final_cost_cents: 95000,
        currency: 'USD',
        verified_by_name: 'Mo Manager',
        verified_at: '2026-11-12T09:00:00Z',
        cost_check: { estimate_cents: 80000, over_estimate_cents: 15000, above_approval: true },
      }),
    )

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    const outcome = (await screen.findByRole('heading', { name: 'Outcome' })).closest(
      'section',
    ) as HTMLElement
    const notes = within(outcome).getAllByRole('note')
    expect(notes[0]).toHaveTextContent('$150.00 more than the estimate of $800.00')
    expect(notes[1]).toHaveTextContent("above the property's approval threshold")
  })
})

// --- The property owner's side ----------------------------------------------------------

function summary(overrides: Partial<ApprovalSummary> = {}): ApprovalSummary {
  return {
    id: 'e-1',
    version: 1,
    reference: 'WO-0001',
    title: 'Replace water heater',
    work_order_status: 'awaiting_approval',
    property_name: 'Oak Terrace',
    location: 'No. 1',
    amount_cents: 145000,
    currency: 'USD',
    status: 'pending',
    current: true,
    decidable: true,
    submitted_at: '2026-11-10T10:00:00Z',
    decided_at: null,
    ...overrides,
  }
}

function approval(overrides: Partial<Approval> = {}): Approval {
  const base = summary()
  return {
    ...base,
    description: 'Replace the failed water heater.',
    provider_name: 'Cascade Heating',
    submitted_by_name: 'Mo Manager',
    decided_by_name: null,
    decision_reason: null,
    threshold_cents: 25000,
    scope: 'No hot water since last night.',
    category: 'plumbing',
    priority: 'emergency',
    due_date: null,
    street: '8 Oak Terrace',
    city: 'Beaverton',
    region: 'OR',
    postal_code: '97005',
    versions: [
      {
        id: 'e-1',
        version: 1,
        amount_cents: 145000,
        currency: 'USD',
        description: 'Replace the failed water heater.',
        provider_name: 'Cascade Heating',
        status: 'pending',
        approval_required: true,
        current: true,
        submitted_by_name: 'Mo Manager',
        submitted_at: '2026-11-10T10:00:00Z',
        decided_by_name: null,
        decided_at: null,
        decision_reason: null,
      },
    ],
    ...overrides,
  }
}

function openAsOwner(routes: Parameters<typeof mockApi>[0]) {
  return mockApi({ 'GET /api/auth/me': { body: sessionFor([asOwner]) }, ...routes })
}

describe('the property owner’s approvals', () => {
  it('gives owners a link in the menu and nothing from the internal side', async () => {
    openAsOwner({ [`GET ${ORG}/my-approvals`]: { body: [] } })

    renderAt(`${ORG_PATH}/my-approvals`)

    expect(await screen.findByText(/Nothing needs your decision/)).toBeInTheDocument()
    const menu = screen.getByRole('navigation', { name: 'Main' })
    expect(within(menu).getByRole('link', { name: 'Approvals' })).toBeInTheDocument()
    expect(within(menu).queryByRole('link', { name: 'Work orders' })).not.toBeInTheDocument()
  })

  it('separates what waits for a decision from earlier estimates', async () => {
    openAsOwner({
      [`GET ${ORG}/my-approvals`]: {
        body: [
          summary(),
          summary({
            id: 'e-2',
            title: 'New dishwasher',
            amount_cents: 132000,
            status: 'approved',
            decidable: false,
            decided_at: '2026-11-09T10:00:00Z',
          }),
        ],
      },
    })

    renderAt(`${ORG_PATH}/my-approvals`)

    const waiting = await screen.findByRole('region', { name: 'Waiting for your decision' })
    expect(within(waiting).getByText('Replace water heater')).toBeInTheDocument()
    expect(within(waiting).getByText('$1,450.00')).toBeInTheDocument()
    const earlier = screen.getByRole('region', { name: 'Earlier estimates' })
    expect(within(earlier).getByText('New dishwasher')).toBeInTheDocument()
    expect(within(earlier).getByText('Approved')).toBeInTheDocument()
  })

  it('shows the work, the amount and the threshold before the decision', async () => {
    openAsOwner({ [`GET ${ORG}/my-approvals/e-1`]: { body: approval() } })

    renderAt(`${ORG_PATH}/my-approvals/e-1`)

    expect(await screen.findByRole('heading', { name: 'Replace water heater' })).toBeInTheDocument()
    expect(screen.getByText('No hot water since last night.')).toBeInTheDocument()
    expect(screen.getByText(/8 Oak Terrace, Beaverton, OR 97005/)).toBeInTheDocument()
    expect(screen.getByText('$1,450.00')).toBeInTheDocument()
    expect(screen.getByText(/threshold was \$250\.00/)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Your decision' })).toBeInTheDocument()
  })

  it('approves, and shows the decision that was recorded', async () => {
    let current = approval()
    const { requests } = openAsOwner({
      [`GET ${ORG}/my-approvals/e-1`]: () => ({ body: current }),
      [`POST ${ORG}/my-approvals/e-1/decision`]: () => {
        current = approval({
          status: 'approved',
          decidable: false,
          decided_by_name: 'Olive Owner',
          decided_at: '2026-11-11T10:00:00Z',
          decision_reason: 'Go ahead.',
        })
        return { body: current }
      },
    })

    renderAt(`${ORG_PATH}/my-approvals/e-1`)
    const form = await screen.findByRole('form', { name: 'Your decision' })
    fireEvent.change(within(form).getByLabelText('Reason (needed to reject)'), {
      target: { value: 'Go ahead.' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText(/Approved by Olive Owner/)).toHaveTextContent(': Go ahead.')
    expect(screen.queryByRole('form', { name: 'Your decision' })).not.toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      decision: 'approve',
      reason: 'Go ahead.',
    })
  })

  it('will not reject without a reason', async () => {
    const { requests } = openAsOwner({
      [`GET ${ORG}/my-approvals/e-1`]: { body: approval() },
      [`POST ${ORG}/my-approvals/e-1/decision`]: { body: approval({ status: 'rejected' }) },
    })

    renderAt(`${ORG_PATH}/my-approvals/e-1`)
    const form = await screen.findByRole('form', { name: 'Your decision' })
    fireEvent.click(within(form).getByRole('button', { name: 'Reject' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('Say why')
    expect(requests.some((request) => request.method === 'POST')).toBe(false)

    fireEvent.change(within(form).getByLabelText('Reason (needed to reject)'), {
      target: { value: 'Get a second quote.' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      decision: 'reject',
      reason: 'Get a second quote.',
    })
  })

  it('shows a refusal from the server instead of pretending it worked', async () => {
    openAsOwner({
      [`GET ${ORG}/my-approvals/e-1`]: { body: approval() },
      [`POST ${ORG}/my-approvals/e-1/decision`]: {
        status: 409,
        body: { detail: 'A decision has already been recorded for this estimate' },
      },
    })

    renderAt(`${ORG_PATH}/my-approvals/e-1`)
    const form = await screen.findByRole('form', { name: 'Your decision' })
    fireEvent.click(within(form).getByRole('button', { name: 'Approve' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('already been recorded')
  })

  it('has no decision form for an estimate that is no longer theirs to decide', async () => {
    openAsOwner({
      [`GET ${ORG}/my-approvals/e-1`]: {
        body: approval({
          decidable: false,
          current: false,
          versions: [
            { ...approval().versions[0], current: false },
            { ...approval().versions[0], id: 'e-2', version: 2, amount_cents: 99000 },
          ],
        }),
      },
    })

    renderAt(`${ORG_PATH}/my-approvals/e-1`)

    expect(await screen.findByText(/A newer estimate has replaced this one/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See the current estimate' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/my-approvals/e-2`,
    )
    expect(screen.queryByRole('form', { name: 'Your decision' })).not.toBeInTheDocument()
  })

  it('is not available to anyone who is not a property owner', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asManager]) } })

    renderAt(`${ORG_PATH}/my-approvals`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('shows a missing estimate as not found', async () => {
    openAsOwner({
      [`GET ${ORG}/my-approvals/e-9`]: { status: 404, body: { detail: 'Estimate not found' } },
    })

    renderAt(`${ORG_PATH}/my-approvals/e-9`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
