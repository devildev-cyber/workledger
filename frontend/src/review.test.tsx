import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type { Membership, Property, Unit, WorkOrder, WorkOrderSummary } from './api/types.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }

function workOrder(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'w-1',
    reference: 'WO-0001',
    title: 'Replace kitchen tap',
    status: 'ready_for_review',
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
    history: [
      {
        id: 'h-1',
        kind: 'status_changed',
        visibility: 'internal',
        body: 'Fitted a new cartridge and tested it',
        status: 'ready_for_review',
        details: null,
        author_name: 'Casey Carpenter',
        created_at: '2026-11-11T10:00:00Z',
      },
    ],
    allowed_statuses: [],
    assignment: null,
    assignment_history: [],
    attachments: [],
    property_currency: 'USD',
    resolution: null,
    verified_by_name: null,
    verified_at: null,
    estimates: [],
    approval_threshold_cents: null,
    owner_names: [],
    approval_hold: null,
    can_record_estimate: true,
    cost_check: null,
    ...overrides,
  }
}

function completed(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return workOrder({
    status: 'completed',
    allowed_statuses: ['in_progress', 'closed'],
    resolution: 'Replaced the cartridge.',
    final_cost_cents: 18550,
    currency: 'USD',
    verified_by_name: 'Mo Manager',
    verified_at: '2026-11-12T09:00:00Z',
    ...overrides,
  })
}

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function open(routes: Record<string, Parameters<typeof mockApi>[0][string]>) {
  return mockApi({
    'GET /api/auth/me': { body: sessionFor([asManager]) },
    [`GET ${ORG}/contractors`]: { body: [] },
    ...routes,
  })
}

describe('reviewing finished work', () => {
  it('shows the contractor’s note and files, and no plain status form', async () => {
    open({
      [`GET ${ORG}/work-orders/w-1`]: {
        body: workOrder({
          attachments: [
            {
              id: 'f-1',
              filename: 'after.png',
              content_type: 'image/png',
              size_bytes: 2048,
              contractor_visible: true,
              uploaded_by_name: 'Casey Carpenter',
              created_at: '2026-11-11T10:00:00Z',
            },
          ],
        }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(await screen.findByText(/marked this work ready for review/)).toBeInTheDocument()
    // Once in the review box, and once in the history it came from.
    expect(screen.getAllByText('Fitted a new cartridge and tested it')).toHaveLength(2)
    expect(screen.getByText(/1 photo or document is attached/)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Verify the work' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Change status' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Outcome' })).not.toBeInTheDocument()
  })

  it('says when no files were attached', async () => {
    open({ [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() } })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(await screen.findByText('No photos or documents are attached.')).toBeInTheDocument()
  })

  it('verifies with a resolution and an exact cost, then shows the outcome', async () => {
    let current = workOrder()
    const { requests } = open({
      [`GET ${ORG}/work-orders/w-1`]: () => ({ body: current }),
      [`POST ${ORG}/work-orders/w-1/verify`]: () => {
        current = completed()
        return { body: current }
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Verify the work' })
    expect(within(form).getByLabelText('Currency')).toHaveValue('USD')

    fireEvent.click(within(form).getByRole('button', { name: 'Verify and complete' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Describe what was done.')

    fireEvent.change(within(form).getByLabelText('What was done'), {
      target: { value: 'Replaced the cartridge.' },
    })
    fireEvent.change(within(form).getByLabelText('Final cost (optional)'), {
      target: { value: '1,85x' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Verify and complete' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('such as 185.50')

    fireEvent.change(within(form).getByLabelText('Final cost (optional)'), {
      target: { value: '185.50' },
    })
    fireEvent.change(within(form).getByLabelText('Currency'), { target: { value: 'us' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Verify and complete' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('three-letter code')
    expect(requests.some((request) => request.method === 'POST')).toBe(false)

    fireEvent.change(within(form).getByLabelText('Currency'), { target: { value: 'usd' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Verify and complete' }))

    const outcome = await screen.findByRole('heading', { name: 'Outcome' })
    const section = outcome.closest('section') as HTMLElement
    expect(within(section).getByText('Replaced the cartridge.')).toBeInTheDocument()
    expect(within(section).getByText(/185\.50/)).toBeInTheDocument()
    expect(within(section).getByText(/Mo Manager/)).toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      resolution: 'Replaced the cartridge.',
      final_cost_cents: 18550,
      currency: 'USD',
    })
    expect(screen.queryByRole('form', { name: 'Verify the work' })).not.toBeInTheDocument()
    expect(await screen.findByRole('form', { name: 'Change status' })).toBeInTheDocument()
    const options = within(screen.getByLabelText('New status')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toContain('Closed')
  })

  it('can verify without recording a cost', async () => {
    const { requests } = open({
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
      [`POST ${ORG}/work-orders/w-1/verify`]: {
        body: completed({ final_cost_cents: null, currency: null }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Verify the work' })
    fireEvent.change(within(form).getByLabelText('What was done'), {
      target: { value: 'All good' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Verify and complete' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      resolution: 'All good',
      final_cost_cents: null,
      currency: null,
    })
  })

  it('shows a refusal from the server', async () => {
    open({
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
      [`POST ${ORG}/work-orders/w-1/verify`]: {
        status: 409,
        body: { detail: 'Only work that is ready for review can be verified or sent back' },
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Verify the work' })
    fireEvent.change(within(form).getByLabelText('What was done'), { target: { value: 'Done' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Verify and complete' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('ready for review')
  })

  it('sends the work back with a reason', async () => {
    let current = workOrder()
    const { requests } = open({
      [`GET ${ORG}/work-orders/w-1`]: () => ({ body: current }),
      [`POST ${ORG}/work-orders/w-1/send-back`]: () => {
        current = workOrder({ status: 'in_progress', allowed_statuses: ['on_hold', 'cancelled'] })
        return { body: current }
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Send back instead' }))
    const form = screen.getByRole('form', { name: 'Send back' })
    expect(screen.queryByRole('form', { name: 'Verify the work' })).not.toBeInTheDocument()

    fireEvent.click(within(form).getByRole('button', { name: 'Send back' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Say what still needs doing.')

    fireEvent.change(within(form).getByLabelText('What still needs doing?'), {
      target: { value: 'It still drips when cold' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Send back' }))

    expect(await screen.findByRole('form', { name: 'Change status' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Send back' })).not.toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      reason: 'It still drips when cold',
    })
  })

  it('goes back to the review from the send back form', async () => {
    open({ [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() } })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Send back instead' }))
    fireEvent.click(screen.getByRole('button', { name: 'Back to review' }))

    expect(screen.getByRole('form', { name: 'Verify the work' })).toBeInTheDocument()
  })

  it('describes reviews in the history', async () => {
    const entry = (
      kind: WorkOrder['history'][number]['kind'],
      body: string,
      details: Record<string, unknown> | null,
    ) => ({
      id: `h-${kind}`,
      kind,
      visibility: 'internal' as const,
      body,
      status: null,
      details,
      author_name: 'Mo Manager',
      created_at: '2026-11-12T09:00:00Z',
    })
    open({
      [`GET ${ORG}/work-orders/w-1`]: {
        body: completed({
          history: [
            entry('sent_back', 'Still dripping', null),
            entry('verified', 'Replaced the cartridge.', {
              final_cost_cents: 18550,
              currency: 'USD',
            }),
            entry('verified', 'Second look', { final_cost_cents: null, currency: null }),
          ],
        }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    const history = await screen.findByRole('list', { name: 'History' })
    expect(within(history).getByText('Sent back to the contractor')).toBeInTheDocument()
    expect(within(history).getAllByText('Work verified')).toHaveLength(2)
    expect(within(history).getByText(/Final cost:.*185\.50/)).toBeInTheDocument()
    expect(within(history).getByText('Final cost: not recorded')).toBeInTheDocument()
  })

  it('shows no outcome for work that has not been verified', async () => {
    open({
      [`GET ${ORG}/work-orders/w-1`]: {
        body: workOrder({ status: 'in_progress', allowed_statuses: ['on_hold'] }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    await screen.findByRole('form', { name: 'Change status' })
    expect(screen.queryByRole('heading', { name: 'Outcome' })).not.toBeInTheDocument()
  })
})

describe('maintenance history', () => {
  const MAPLE = 'p-maple'
  const maple: Property = {
    id: MAPLE,
    name: 'Maple Court',
    street: '12 Maple Street',
    city: 'Springfield',
    region: 'IL',
    postal_code: '62701',
    currency: 'USD',
    approval_threshold_cents: null,
    unit_count: 2,
    buildings: [],
  }
  const units: Unit[] = [
    { id: 'u-1', property_id: MAPLE, building_id: null, label: '1A', current_residents: [] },
    { id: 'u-2', property_id: MAPLE, building_id: null, label: '2B', current_residents: [] },
  ]

  function summary(overrides: Partial<WorkOrderSummary>): WorkOrderSummary {
    const {
      scope,
      linked_requests,
      history,
      allowed_statuses,
      assignment,
      assignment_history,
      attachments,
      property_currency,
      resolution,
      verified_by_name,
      verified_at,
      ...rest
    } = completed()
    void [
      scope,
      linked_requests,
      history,
      allowed_statuses,
      assignment,
      assignment_history,
      attachments,
      property_currency,
      resolution,
      verified_by_name,
      verified_at,
    ]
    return { ...rest, ...overrides }
  }

  it('lists finished work with its cost, and narrows to one unit', async () => {
    const first = summary({ id: 'w-1', title: 'Replace kitchen tap', unit_label: '1A' })
    const second = summary({
      id: 'w-2',
      reference: 'WO-0002',
      title: 'Fix the gutter',
      unit_label: null,
      status: 'closed',
      final_cost_cents: null,
      currency: null,
    })
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties/${MAPLE}`]: { body: maple },
      [`GET ${ORG}/properties/${MAPLE}/units`]: { body: units },
      [`GET ${ORG}/work-orders?property_id=${MAPLE}&history_only=true`]: { body: [first, second] },
      [`GET ${ORG}/work-orders?property_id=${MAPLE}&history_only=true&unit_id=u-1`]: {
        body: [first],
      },
    })

    renderAt(`${ORG_PATH}/properties/${MAPLE}`)

    const heading = await screen.findByRole('heading', { name: 'Maintenance history' })
    const section = heading.closest('section') as HTMLElement
    const table = await within(section).findByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Replace kitchen tap')
    expect(rows[0]).toHaveTextContent('185.50')
    expect(rows[1]).toHaveTextContent('Common areas')
    expect(within(rows[0]).getByRole('link', { name: 'Replace kitchen tap' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/work-orders/w-1`,
    )

    await within(section).findByRole('option', { name: '1A' })
    fireEvent.change(within(section).getByLabelText('Unit'), { target: { value: 'u-1' } })

    await waitFor(() =>
      expect(within(section).queryByText('Fix the gutter')).not.toBeInTheDocument(),
    )
    expect(within(section).getByText('Replace kitchen tap')).toBeInTheDocument()
    expect(requests.map((request) => request.path)).toContain(
      `${ORG}/work-orders?property_id=${MAPLE}&history_only=true&unit_id=u-1`,
    )
  })

  it('explains an empty history', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties/${MAPLE}`]: { body: maple },
      [`GET ${ORG}/properties/${MAPLE}/units`]: { body: units },
      [`GET ${ORG}/work-orders?property_id=${MAPLE}&history_only=true`]: { body: [] },
    })

    renderAt(`${ORG_PATH}/properties/${MAPLE}`)

    expect(await screen.findByText(/No finished work yet/)).toBeInTheDocument()
  })
})
