import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type {
  Membership,
  StaffRequest,
  StaffRequestSummary,
  WorkOrder,
  WorkOrderSummary,
} from './api/types.ts'
import { groupRequests } from './requests/queue.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asResident: Membership = { ...harborAdmin, roles: ['resident'] }

function staffRequest(overrides: Partial<StaffRequest> = {}): StaffRequest {
  return {
    id: 'r-1',
    reference: 'REQ-0001',
    status: 'submitted',
    category: 'plumbing',
    urgency: 'soon',
    title: 'Kitchen tap drips',
    property_name: 'Maple Court',
    unit_label: '1A',
    building_name: 'Building A',
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    property_id: 'p-1',
    resident_name: 'Rae Resident',
    submitted_on_behalf: false,
    work_order: null,
    needs_triage: true,
    duplicate_of: null,
    description: 'The cold tap has dripped all week.',
    location: 'Kitchen',
    access_notes: null,
    resident: {
      id: 'res-1',
      full_name: 'Rae Resident',
      email: null,
      phone: null,
      access_instructions: null,
      has_account: true,
    },
    timeline: [],
    attachments: [],
    ...overrides,
  }
}

function workOrder(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'w-1',
    reference: 'WO-0001',
    title: 'Replace kitchen tap',
    status: 'open',
    priority: 'soon',
    category: 'plumbing',
    property_id: 'p-1',
    property_name: 'Maple Court',
    unit_label: '1A',
    building_name: 'Building A',
    due_date: '2026-12-01',
    overdue: false,
    request_count: 1,
    assignee_id: null,
    assignee_name: null,
    assignment_response: null,
    final_cost_cents: null,
    currency: null,
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    scope: 'Fit a new cartridge.',
    linked_requests: [
      {
        id: 'r-1',
        reference: 'REQ-0001',
        title: 'Kitchen tap drips',
        status: 'in_review',
        resident_name: 'Rae Resident',
      },
    ],
    history: [
      {
        id: 'h-1',
        kind: 'created',
        visibility: 'internal',
        body: null,
        status: 'open',
        details: null,
        author_name: 'Mo Manager',
        created_at: '2026-11-10T10:00:00Z',
      },
    ],
    allowed_statuses: ['in_progress', 'on_hold', 'cancelled'],
    assignment: null,
    assignment_history: [],
    attachments: [],
    property_currency: 'USD',
    resolution: null,
    verified_by_name: null,
    verified_at: null,
    ...overrides,
  }
}

function summaryOf(order: WorkOrder): WorkOrderSummary {
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
  } = order
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
  return rest
}

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('navigation and access', () => {
  it('gives staff a Work orders link and residents none', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asManager]) } })
    const { unmount } = renderAt(ORG_PATH)
    expect(await screen.findByRole('link', { name: 'Work orders' })).toBeInTheDocument()
    unmount()

    mockApi({ 'GET /api/auth/me': { body: sessionFor([asResident]) } })
    renderAt(ORG_PATH)
    await screen.findByRole('link', { name: 'My requests' })
    expect(screen.queryByRole('link', { name: 'Work orders' })).not.toBeInTheDocument()
  })

  it.each(['/work-orders', '/work-orders/w-1'])('keeps a resident away from %s', async (path) => {
    const { requests } = mockApi({ 'GET /api/auth/me': { body: sessionFor([asResident]) } })
    renderAt(`${ORG_PATH}${path}`)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(requests).toHaveLength(1)
  })
})

describe('triage on a request', () => {
  it('offers the three ways to deal with a new request', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)

    const panel = await screen.findByRole('region', { name: 'Triage' })
    expect(within(panel).getByRole('button', { name: 'Create work order' })).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Mark as duplicate' })).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Decline' })).toBeInTheDocument()
  })

  it('turns the request into a work order, prefilled, and opens it', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
      [`POST ${ORG}/requests/r-1/convert`]: { status: 201, body: workOrder() },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Create work order' }))
    const form = screen.getByRole('form', { name: 'Create work order' })
    expect(within(form).getByLabelText('Title')).toHaveValue('Kitchen tap drips')
    expect(within(form).getByLabelText('Scope of work')).toHaveValue('The cold tap has dripped all week.')
    expect(within(form).getByLabelText('Priority')).toHaveValue('soon')
    fireEvent.change(within(form).getByLabelText('Priority'), { target: { value: 'urgent' } })
    fireEvent.change(within(form).getByLabelText('Due date'), { target: { value: '2026-12-01' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Create work order' }))

    expect(await screen.findByRole('heading', { name: 'Replace kitchen tap' })).toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      title: 'Kitchen tap drips',
      scope: 'The cold tap has dripped all week.',
      category: 'plumbing',
      priority: 'urgent',
      due_date: '2026-12-01',
    })
  })

  it('marks a request as a duplicate of another open report at the same property', async () => {
    const original = { ...staffRequest({ id: 'r-2', reference: 'REQ-0002', title: 'Tap leaks' }) }
    const done = { ...staffRequest({ id: 'r-3', reference: 'REQ-0003', status: 'closed' }) }
    const linked = staffRequest({
      status: 'in_review',
      needs_triage: false,
      duplicate_of: { id: 'r-2', reference: 'REQ-0002' },
    })
    let current = staffRequest()
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: () => ({ body: current }),
      [`GET ${ORG}/requests?property_id=p-1`]: { body: [staffRequest(), original, done] },
      [`POST ${ORG}/requests/r-1/duplicate`]: () => {
        current = linked
        return { body: linked }
      },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Mark as duplicate' }))
    const form = screen.getByRole('form', { name: 'Mark as duplicate' })
    const choose = within(form).getByLabelText('Original request')
    await within(form).findByRole('option', { name: 'REQ-0002 · Tap leaks' })
    // Not itself, and not a request that is already finished.
    expect(within(choose).queryByRole('option', { name: /REQ-0001/ })).not.toBeInTheDocument()
    expect(within(choose).queryByRole('option', { name: /REQ-0003/ })).not.toBeInTheDocument()

    fireEvent.click(within(form).getByRole('button', { name: 'Mark as duplicate' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Choose the original request.')

    fireEvent.change(choose, { target: { value: 'r-2' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Mark as duplicate' }))

    expect(await screen.findByText('Duplicate of')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'REQ-0002' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/requests/r-2`,
    )
    expect(screen.queryByRole('region', { name: 'Triage' })).not.toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      duplicate_of_id: 'r-2',
    })
  })

  it('declines with a reason the resident will read', async () => {
    const declined = staffRequest({ status: 'declined', needs_triage: false })
    let current = staffRequest()
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: () => ({ body: current }),
      [`POST ${ORG}/requests/r-1/decline`]: () => {
        current = declined
        return { body: declined }
      },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Decline' }))
    const form = screen.getByRole('form', { name: 'Decline request' })

    fireEvent.click(within(form).getByRole('button', { name: 'Decline request' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Tell the resident why')
    expect(requests.some((request) => request.method === 'POST')).toBe(false)

    fireEvent.change(within(form).getByLabelText('Reason for the resident'), {
      target: { value: 'This is the owner’s fixture.' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Decline request' }))

    expect(await screen.findAllByText('Declined')).not.toHaveLength(0)
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      reason: 'This is the owner’s fixture.',
    })
  })

  it('shows the server message when triage is refused', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
      [`POST ${ORG}/requests/r-1/decline`]: {
        status: 409,
        body: { detail: 'This request has already been dealt with' },
      },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Decline' }))
    fireEvent.change(screen.getByLabelText('Reason for the resident'), { target: { value: 'No' + 'pe' } })
    fireEvent.click(screen.getByRole('button', { name: 'Decline request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already been dealt with')
  })

  it('hides triage once there is a work order and says the status follows it', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: {
        body: staffRequest({
          status: 'in_progress',
          needs_triage: false,
          work_order: { id: 'w-1', reference: 'WO-0001', status: 'in_progress' },
        }),
      },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)

    const link = await screen.findByRole('link', { name: 'WO-0001' })
    expect(link).toHaveAttribute('href', `${ORG_PATH}/work-orders/w-1`)
    expect(screen.queryByRole('region', { name: 'Triage' })).not.toBeInTheDocument()
    const form = screen.getByRole('form', { name: 'Update request' })
    expect(within(form).queryByLabelText('Change status')).not.toBeInTheDocument()
    expect(within(form).getByText(/follows its work order/)).toBeInTheDocument()
  })

  it('does not offer Declined as a plain status change', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest({ needs_triage: false }) },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)

    const select = await screen.findByLabelText('Change status')
    expect(within(select).queryByRole('option', { name: 'Declined' })).not.toBeInTheDocument()
  })
})

describe('work order list', () => {
  const properties = [{ id: 'p-1', name: 'Maple Court' }]

  it('shows open work orders with their due dates and overdue warnings', async () => {
    const late = workOrder({ id: 'w-2', reference: 'WO-0002', title: 'Fix the gutter', overdue: true })
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: properties },
      [`GET ${ORG}/work-orders?open_only=true`]: { body: [summaryOf(workOrder()), summaryOf(late)] },
    })

    renderAt(`${ORG_PATH}/work-orders`)

    const link = await screen.findByRole('link', { name: 'Replace kitchen tap' })
    expect(link).toHaveAttribute('href', `${ORG_PATH}/work-orders/w-1`)
    expect(screen.getByText('WO-0002')).toBeInTheDocument()
    expect(screen.getAllByText('Overdue')).toHaveLength(1)
  })

  it('sends filters and search to the server', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: properties },
      [`GET ${ORG}/work-orders?open_only=true`]: { body: [summaryOf(workOrder())] },
      [`GET ${ORG}/work-orders`]: { body: [] },
      [`GET ${ORG}/work-orders?status=on_hold`]: { body: [] },
      [`GET ${ORG}/work-orders?status=on_hold&priority=urgent&property_id=p-1&older_than_days=7`]: { body: [] },
      [`GET ${ORG}/work-orders?status=on_hold&priority=urgent&property_id=p-1&q=WO-0001&older_than_days=7`]: {
        body: [summaryOf(workOrder())],
      },
    })

    renderAt(`${ORG_PATH}/work-orders`)
    await screen.findByText('Replace kitchen tap')
    await screen.findByRole('option', { name: 'Maple Court' })

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'on_hold' } })
    expect(await screen.findByText('No work orders match these filters.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: 'urgent' } })
    fireEvent.change(screen.getByLabelText('Property'), { target: { value: 'p-1' } })
    fireEvent.change(screen.getByLabelText('Age'), { target: { value: '7' } })
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'WO-0001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Replace kitchen tap')).toBeInTheDocument()
    expect(requests.at(-1)?.path).toContain('q=WO-0001')
  })

  it('says so when there are none', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: properties },
      [`GET ${ORG}/work-orders?open_only=true`]: { body: [] },
    })
    renderAt(`${ORG_PATH}/work-orders`)
    expect(await screen.findByText('There are no work orders yet.')).toBeInTheDocument()
  })

  it('raises a work order without a request', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: properties },
      [`GET ${ORG}/work-orders?open_only=true`]: { body: [] },
      [`POST ${ORG}/work-orders`]: { status: 201, body: workOrder({ title: 'Repaint stairwell' }) },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder({ title: 'Repaint stairwell' }) },
    })

    renderAt(`${ORG_PATH}/work-orders`)
    await screen.findByText('There are no work orders yet.')
    await screen.findByRole('option', { name: 'Maple Court' })
    fireEvent.click(screen.getByRole('button', { name: 'New work order' }))
    const form = screen.getByRole('form', { name: 'New work order' })

    fireEvent.click(within(form).getByRole('button', { name: 'Create work order' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Choose a property.')

    fireEvent.change(within(form).getByLabelText('Property'), { target: { value: 'p-1' } })
    fireEvent.change(within(form).getByLabelText('Title'), { target: { value: 'Repaint stairwell' } })
    fireEvent.change(within(form).getByLabelText('Scope of work'), { target: { value: 'Two coats' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Create work order' }))

    expect(await screen.findByRole('heading', { name: 'Repaint stairwell' })).toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      property_id: 'p-1',
      title: 'Repaint stairwell',
      scope: 'Two coats',
      category: 'other',
      priority: 'routine',
      due_date: null,
    })
  })
})

describe('work order page', () => {
  it('is the one place for scope, status, linked requests and history', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(await screen.findByRole('heading', { name: 'Replace kitchen tap' })).toBeInTheDocument()
    expect(screen.getByText('Fit a new cartridge.')).toBeInTheDocument()
    expect(screen.getByText('Building A · 1A, Maple Court')).toBeInTheDocument()
    const requests = screen.getByRole('region', { name: 'Linked requests' })
    expect(within(requests).getByRole('link', { name: 'REQ-0001' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/requests/r-1`,
    )
    const history = screen.getByRole('list', { name: 'History' })
    expect(within(history).getByText('Work order created')).toBeInTheDocument()
    expect(within(history).getByText(/Mo Manager/)).toBeInTheDocument()
  })

  it('offers only the statuses the server allows and sends the choice with a note', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
      [`POST ${ORG}/work-orders/w-1/status`]: { body: workOrder({ status: 'in_progress' }) },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Change status' })
    const select = within(form).getByLabelText('New status')
    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Choose a status',
      'In progress',
      'On hold',
      'Cancelled',
    ])

    fireEvent.click(within(form).getByRole('button', { name: 'Update status' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Choose the new status.')

    fireEvent.change(select, { target: { value: 'in_progress' } })
    fireEvent.change(within(form).getByLabelText('Reason or note (optional)'), {
      target: { value: 'Plumber on site' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Update status' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      status: 'in_progress',
      note: 'Plumber on site',
    })
  })

  it('shows the server message when a move is refused', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
      [`POST ${ORG}/work-orders/w-1/status`]: {
        status: 409,
        body: { detail: 'A work order cannot move from open to completed' },
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Change status' })
    fireEvent.change(within(form).getByLabelText('New status'), { target: { value: 'on_hold' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Update status' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('cannot move from open to completed')
  })

  it('tells a manager a finished work order needs an administrator', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: {
        body: workOrder({ status: 'closed', allowed_statuses: [] }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(await screen.findByText(/An administrator can reopen it/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Change status' })).not.toBeInTheDocument()
  })

  it('shows an overdue warning', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder({ overdue: true }) },
    })
    renderAt(`${ORG_PATH}/work-orders/w-1`)
    expect(await screen.findByText('Overdue')).toBeInTheDocument()
  })

  it('edits the details', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
      [`PUT ${ORG}/work-orders/w-1`]: { body: workOrder({ priority: 'urgent' }) },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit details' }))
    const form = screen.getByRole('form', { name: 'Edit work order' })
    expect(within(form).getByLabelText('Title')).toHaveValue('Replace kitchen tap')
    fireEvent.change(within(form).getByLabelText('Priority'), { target: { value: 'urgent' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(screen.queryByRole('form', { name: 'Edit work order' })).not.toBeInTheDocument())
    expect(requests.find((request) => request.method === 'PUT')?.body).toEqual({
      title: 'Replace kitchen tap',
      scope: 'Fit a new cartridge.',
      category: 'plumbing',
      priority: 'urgent',
      due_date: '2026-12-01',
    })
  })

  it('adds a note that is internal unless shared on purpose', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
      [`POST ${ORG}/work-orders/w-1/notes`]: { status: 201, body: workOrder() },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Add note' })

    fireEvent.click(within(form).getByRole('button', { name: 'Add note' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Write the note first.')

    fireEvent.change(within(form).getByLabelText('Note'), { target: { value: 'Part ordered' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Add note' }))
    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))

    fireEvent.change(within(form).getByLabelText('Note'), { target: { value: 'Visit Thursday' } })
    fireEvent.click(within(form).getByLabelText('Share with the residents of linked requests'))
    fireEvent.click(within(form).getByRole('button', { name: 'Add note' }))
    await waitFor(() => expect(requests.filter((request) => request.method === 'POST')).toHaveLength(2))

    fireEvent.change(within(form).getByLabelText('Note'), { target: { value: 'Use the side gate' } })
    fireEvent.click(within(form).getByLabelText('Internal note, staff only'))
    fireEvent.click(within(form).getByLabelText('Also share with the assigned contractor'))
    fireEvent.click(within(form).getByRole('button', { name: 'Add note' }))
    await waitFor(() => expect(requests.filter((request) => request.method === 'POST')).toHaveLength(3))

    expect(requests.filter((request) => request.method === 'POST').map((request) => request.body)).toEqual([
      { body: 'Part ordered', visibility: 'internal', share_with_contractor: false },
      { body: 'Visit Thursday', visibility: 'resident', share_with_contractor: false },
      { body: 'Use the side gate', visibility: 'internal', share_with_contractor: true },
    ])
  })

  it('describes every kind of history entry', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-1`]: {
        body: workOrder({
          history: [
            ...workOrder().history,
            {
              id: 'h-2',
              kind: 'status_changed',
              visibility: 'internal',
              body: 'Plumber on site',
              status: 'in_progress',
              details: null,
              author_name: 'Mo Manager',
              created_at: '2026-11-11T10:00:00Z',
            },
            {
              id: 'h-3',
              kind: 'edited',
              visibility: 'internal',
              body: null,
              status: null,
              details: { priority: ['soon', 'urgent'], due_date: [null, '2026-12-01'] },
              author_name: 'Mo Manager',
              created_at: '2026-11-12T10:00:00Z',
            },
            {
              id: 'h-4',
              kind: 'note',
              visibility: 'resident',
              body: 'Visit Thursday',
              status: null,
              details: null,
              author_name: 'Mo Manager',
              created_at: '2026-11-12T11:00:00Z',
            },
            {
              id: 'h-5',
              kind: 'request_linked',
              visibility: 'internal',
              body: 'REQ-0002 linked',
              status: null,
              details: null,
              author_name: null,
              created_at: '2026-11-12T12:00:00Z',
            },
          ],
        }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    const history = await screen.findByRole('list', { name: 'History' })
    expect(within(history).getByText('Status changed to In progress')).toBeInTheDocument()
    expect(within(history).getByText('Plumber on site')).toBeInTheDocument()
    expect(within(history).getByText(/Priority: Soon → Urgent/)).toBeInTheDocument()
    expect(within(history).getByText(/Due date: none → /)).toBeInTheDocument()
    expect(within(history).getByText('Shared with residents')).toBeInTheDocument()
    expect(within(history).getByText('REQ-0002 linked')).toBeInTheDocument()
    expect(within(history).getByText(/System/)).toBeInTheDocument()
  })

  it('shows not found for a work order that is not there', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/work-orders/w-9`]: { status: 404, body: { detail: 'Work order not found' } },
    })
    renderAt(`${ORG_PATH}/work-orders/w-9`)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})

describe('grouping the queue', () => {
  const now = new Date('2026-11-12T12:00:00Z')

  function request(id: string, urgency: StaffRequestSummary['urgency'], created: string, property = 'Maple Court') {
    const { timeline, attachments, resident, description, location, access_notes, duplicate_of, ...rest } =
      staffRequest({ id, urgency, created_at: created, property_name: property })
    void [timeline, attachments, resident, description, location, access_notes, duplicate_of]
    return rest
  }

  const queue = [
    request('a', 'routine', '2026-11-12T08:00:00Z'),
    request('b', 'emergency', '2026-11-05T08:00:00Z', 'Oak Terrace'),
    request('c', 'soon', '2026-11-10T08:00:00Z', 'Maple Court'),
  ]

  const ids = (groups: ReturnType<typeof groupRequests>) =>
    groups.map((group) => [group.title, group.requests.map((item) => item.id)])

  it('puts the most urgent first and leaves out empty groups', () => {
    expect(ids(groupRequests(queue, 'urgency', now))).toEqual([
      ['Emergency', ['b']],
      ['Soon', ['c']],
      ['Routine', ['a']],
    ])
  })

  it('puts the oldest first when grouping by age', () => {
    expect(ids(groupRequests(queue, 'age', now))).toEqual([
      ['Older than a week', ['b']],
      ['Within a week', ['c']],
      ['Today', ['a']],
    ])
  })

  it('orders properties by name', () => {
    expect(ids(groupRequests(queue, 'property', now))).toEqual([
      ['Maple Court', ['a', 'c']],
      ['Oak Terrace', ['b']],
    ])
  })

  it('can leave the queue as one list', () => {
    expect(ids(groupRequests(queue, 'none', now))).toEqual([['All', ['a', 'b', 'c']]])
  })
})
