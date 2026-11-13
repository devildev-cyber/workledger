import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type {
  Assignment,
  Contractor,
  Job,
  JobSummary,
  Membership,
  WorkOrder,
  WorkOrderSummary,
} from './api/types.ts'
import { groupJobs } from './jobs/labels.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asResident: Membership = { ...harborAdmin, roles: ['resident'] }
const asContractor: Membership = { ...harborAdmin, roles: ['contractor'] }

const CONTRACTORS: Contractor[] = [
  { id: 'c-1', full_name: 'Casey Carpenter', email: 'casey@example.com', active_jobs: 2 },
  { id: 'c-2', full_name: 'Pat Plumber', email: 'pat@example.com', active_jobs: 1 },
]

function assignment(overrides: Partial<Assignment> = {}): Assignment {
  return {
    id: 'a-1',
    contractor_id: 'c-1',
    contractor_name: 'Casey Carpenter',
    assigned_by_name: 'Mo Manager',
    assigned_at: '2026-11-10T10:00:00Z',
    response: 'pending',
    responded_at: null,
    decline_reason: null,
    ended_at: null,
    ended_reason: null,
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
    building_name: null,
    due_date: '2026-12-01',
    overdue: false,
    request_count: 0,
    assignee_id: null,
    assignee_name: null,
    assignment_response: null,
    final_cost_cents: null,
    currency: null,
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    scope: 'Fit a new cartridge.',
    linked_requests: [],
    history: [],
    allowed_statuses: ['in_progress', 'on_hold', 'cancelled'],
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

function assigned(overrides: Partial<WorkOrder> = {}): WorkOrder {
  const current = assignment()
  return workOrder({
    status: 'assigned',
    assignee_id: current.contractor_id,
    assignee_name: current.contractor_name,
    assignment_response: current.response,
    assignment: current,
    assignment_history: [current],
    ...overrides,
  })
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

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: 'w-1',
    reference: 'WO-0001',
    title: 'Replace kitchen tap',
    status: 'assigned',
    priority: 'soon',
    category: 'plumbing',
    due_date: '2026-12-01',
    overdue: false,
    property_name: 'Maple Court',
    unit_label: '1A',
    building_name: 'Building A',
    response: 'pending',
    scope: 'Fit a new cartridge.',
    street: '12 Maple Street',
    city: 'Springfield',
    region: 'IL',
    postal_code: '62701',
    residents: [],
    access_notes: [],
    can_accept: true,
    can_decline: true,
    allowed_statuses: [],
    timeline: [],
    attachments: [],
    ...overrides,
  }
}

function accepted(overrides: Partial<Job> = {}): Job {
  return job({
    response: 'accepted',
    can_accept: false,
    can_decline: false,
    residents: ['Rae'],
    access_notes: ['Ring the bell, I work from home'],
    allowed_statuses: ['in_progress'],
    ...overrides,
  })
}

function summaryOfJob(item: Job): JobSummary {
  return {
    id: item.id,
    reference: item.reference,
    title: item.title,
    status: item.status,
    priority: item.priority,
    category: item.category,
    due_date: item.due_date,
    overdue: item.overdue,
    property_name: item.property_name,
    unit_label: item.unit_label,
    building_name: item.building_name,
    response: item.response,
  }
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
  it('gives contractors a My jobs link and no staff links', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asContractor]) } })

    renderAt(ORG_PATH)

    expect(await screen.findByRole('link', { name: 'My jobs' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/my-jobs`,
    )
    expect(screen.queryByRole('link', { name: 'Work orders' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Requests' })).not.toBeInTheDocument()
  })

  it.each([
    ['manager', asManager],
    ['resident', asResident],
  ])('keeps a %s out of the job workspace', async (_name, membership) => {
    const { requests } = mockApi({ 'GET /api/auth/me': { body: sessionFor([membership]) } })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'My jobs' })).not.toBeInTheDocument()
    expect(requests).toHaveLength(1)
  })

  it.each(['/work-orders', '/work-orders/w-1', '/requests'])(
    'keeps a contractor away from %s',
    async (path) => {
      const { requests } = mockApi({ 'GET /api/auth/me': { body: sessionFor([asContractor]) } })

      renderAt(`${ORG_PATH}${path}`)

      expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
      expect(requests).toHaveLength(1)
    },
  )
})

describe('assigning a work order', () => {
  it('assigns a contractor and shows who has it and whether they replied', async () => {
    let current = workOrder()
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: () => ({ body: current }),
      [`POST ${ORG}/work-orders/w-1/assign`]: () => {
        current = assigned()
        return { body: current }
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Assign a contractor' })
    expect(screen.getByText('No contractor is assigned.')).toBeInTheDocument()
    const choices = within(form)
      .getAllByRole('option')
      .map((option) => option.textContent)
    await waitFor(() =>
      expect(
        within(form)
          .getAllByRole('option')
          .map((option) => option.textContent),
      ).toContain('Casey Carpenter (2 open jobs)'),
    )
    expect(choices.length).toBeGreaterThan(0)
    expect(
      within(form)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toContain('Pat Plumber (1 open job)')

    fireEvent.click(within(form).getByRole('button', { name: 'Assign' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Choose a contractor.')

    fireEvent.change(within(form).getByLabelText('Contractor'), { target: { value: 'c-1' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Assign' }))

    expect(await screen.findByText('Waiting for a reply')).toBeInTheDocument()
    expect(screen.getAllByText(/Casey Carpenter/).length).toBeGreaterThan(0)
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      contractor_id: 'c-1',
    })
  })

  it('reassigns without offering the current contractor, and keeps the history in view', async () => {
    const first = assignment({
      response: 'accepted',
      responded_at: '2026-11-10T12:00:00Z',
      ended_at: '2026-11-11T09:00:00Z',
      ended_reason: 'reassigned',
    })
    const second = assignment({
      id: 'a-2',
      contractor_id: 'c-2',
      contractor_name: 'Pat Plumber',
      assigned_at: '2026-11-11T09:00:00Z',
    })
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: {
        body: assigned({
          assignment: second,
          assignment_history: [first, second],
          assignee_id: 'c-2',
          assignee_name: 'Pat Plumber',
        }),
      },
      [`POST ${ORG}/work-orders/w-1/assign`]: { body: workOrder() },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Reassign' })
    await within(form).findByRole('option', { name: /Casey Carpenter/ })
    expect(within(form).queryByRole('option', { name: /Pat Plumber/ })).not.toBeInTheDocument()

    const history = screen.getByRole('list', { name: 'Assignment history' })
    const rows = within(history).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Casey Carpenter')
    expect(rows[0]).toHaveTextContent('Reassigned on')
    expect(rows[0]).toHaveTextContent('Accepted')
    expect(rows[1]).toHaveTextContent('Pat Plumber')
    expect(rows[1]).toHaveTextContent('Current')

    fireEvent.change(within(form).getByLabelText('Reassign to'), { target: { value: 'c-1' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Reassign' }))
    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      contractor_id: 'c-1',
    })
  })

  it('shows why a contractor turned a job down', async () => {
    const declined = assignment({
      response: 'declined',
      decline_reason: 'Fully booked this week',
      ended_at: '2026-11-11T09:00:00Z',
      ended_reason: 'declined',
    })
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder({ assignment_history: [declined] }) },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    const history = await screen.findByRole('list', { name: 'Assignment history' })
    expect(history).toHaveTextContent('Declined by the contractor')
    expect(history).toHaveTextContent('Reason: Fully booked this week')
  })

  it('removes the contractor', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: { body: assigned() },
      [`POST ${ORG}/work-orders/w-1/unassign`]: { body: workOrder() },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Remove contractor' }))

    await waitFor(() =>
      expect(requests.some((request) => request.path === `${ORG}/work-orders/w-1/unassign`)).toBe(
        true,
      ),
    )
  })

  it('shows a refusal from the server', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
      [`POST ${ORG}/work-orders/w-1/assign`]: {
        status: 409,
        body: { detail: 'This work order can no longer be assigned' },
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const form = await screen.findByRole('form', { name: 'Assign a contractor' })
    await within(form).findByRole('option', { name: /Casey Carpenter/ })
    fireEvent.change(within(form).getByLabelText('Contractor'), { target: { value: 'c-1' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Assign' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'This work order can no longer be assigned',
    )
  })

  it('offers no assignment once the work is waiting for review', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: {
        body: assigned({ status: 'ready_for_review', allowed_statuses: ['completed'] }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(await screen.findByText(/can no longer be assigned or reassigned/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Reassign' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove contractor' })).not.toBeInTheDocument()
  })

  it('says so when nobody holds the contractor role yet', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: [] },
      [`GET ${ORG}/work-orders/w-1`]: { body: workOrder() },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    expect(await screen.findByText(/No one holds the contractor role yet/)).toBeInTheDocument()
  })

  it('shares a file with the contractor only when asked', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: {
        body: workOrder({
          attachments: [
            {
              id: 'f-1',
              filename: 'invoice.pdf',
              content_type: 'application/pdf',
              size_bytes: 2048,
              contractor_visible: false,
              uploaded_by_name: 'Mo Manager',
              created_at: '2026-11-10T10:00:00Z',
            },
            {
              id: 'f-2',
              filename: 'plan.png',
              content_type: 'image/png',
              size_bytes: 2048,
              contractor_visible: true,
              uploaded_by_name: 'Mo Manager',
              created_at: '2026-11-10T10:00:00Z',
            },
          ],
        }),
      },
      [`POST ${ORG}/work-orders/w-1/attachments?filename=plan.png&contractor_visible=true`]: {
        status: 201,
        body: {},
      },
      [`POST ${ORG}/work-orders/w-1/attachments?filename=invoice.pdf&contractor_visible=false`]: {
        status: 201,
        body: {},
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)
    const files = await screen.findByRole('list', { name: 'Files' })
    const items = within(files).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Staff only')
    expect(items[1]).toHaveTextContent('Shared with the contractor')

    const form = screen.getByRole('form', { name: 'Attach a file' })
    fireEvent.change(within(form).getByLabelText('Add a photo or PDF'), {
      target: { files: [new File(['x'], 'invoice.pdf', { type: 'application/pdf' })] },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Upload' }))
    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))

    fireEvent.change(within(form).getByLabelText('Add a photo or PDF'), {
      target: { files: [new File(['x'], 'plan.png', { type: 'image/png' })] },
    })
    fireEvent.click(within(form).getByLabelText('Share with the contractor'))
    fireEvent.click(within(form).getByRole('button', { name: 'Upload' }))
    await waitFor(() =>
      expect(requests.filter((request) => request.method === 'POST')).toHaveLength(2),
    )

    expect(
      requests.filter((request) => request.method === 'POST').map((request) => request.path),
    ).toEqual([
      `${ORG}/work-orders/w-1/attachments?filename=invoice.pdf&contractor_visible=false`,
      `${ORG}/work-orders/w-1/attachments?filename=plan.png&contractor_visible=true`,
    ])
  })

  it('describes the new kinds of history entry', async () => {
    const entry = (kind: WorkOrder['history'][number]['kind'], body: string | null) => ({
      id: `h-${kind}`,
      kind,
      visibility: 'internal' as const,
      body,
      status: null,
      details: null,
      author_name: 'Casey Carpenter',
      created_at: '2026-11-10T10:00:00Z',
    })
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders/w-1`]: {
        body: workOrder({
          history: [
            entry('assigned', 'Assigned to Casey Carpenter'),
            entry('assignment_accepted', null),
            entry('progress', 'Half done'),
            entry('clarification', 'Is the cabinet in scope?'),
            entry('assignment_declined', 'Too far away'),
            entry('unassigned', 'Contractor removed'),
          ],
        }),
      },
    })

    renderAt(`${ORG_PATH}/work-orders/w-1`)

    const history = await screen.findByRole('list', { name: 'History' })
    for (const text of [
      'Contractor assigned',
      'Job accepted',
      'Progress update',
      'Question for the property team',
      'Job declined',
      'Contractor removed',
    ]) {
      expect(within(history).getAllByText(text).length).toBeGreaterThan(0)
    }
  })
})

describe('work order list', () => {
  const properties = [{ id: 'p-1', name: 'Maple Court' }]

  it('shows the contractor on each work order and filters by contractor', async () => {
    const mine = assigned()
    const free = workOrder({ id: 'w-2', reference: 'WO-0002', title: 'Paint the hall' })
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: properties },
      [`GET ${ORG}/contractors`]: { body: CONTRACTORS },
      [`GET ${ORG}/work-orders?open_only=true`]: { body: [summaryOf(mine), summaryOf(free)] },
      [`GET ${ORG}/work-orders?open_only=true&unassigned=true`]: { body: [summaryOf(free)] },
      [`GET ${ORG}/work-orders?open_only=true&assignee_id=c-1`]: { body: [summaryOf(mine)] },
    })

    renderAt(`${ORG_PATH}/work-orders`)
    const row = (await screen.findByText('Replace kitchen tap')).closest('tr')
    expect(row).toHaveTextContent('Casey Carpenter')
    expect(row).toHaveTextContent('Waiting for a reply')

    await screen.findByRole('option', { name: 'Casey Carpenter' })
    fireEvent.change(screen.getByLabelText('Contractor'), { target: { value: 'none' } })
    await waitFor(() => expect(screen.queryByText('Replace kitchen tap')).not.toBeInTheDocument())
    expect(screen.getByText('Paint the hall')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Contractor'), { target: { value: 'c-1' } })
    expect(await screen.findByText('Replace kitchen tap')).toBeInTheDocument()
    expect(screen.queryByText('Paint the hall')).not.toBeInTheDocument()
    expect(requests.map((request) => request.path)).toContain(
      `${ORG}/work-orders?open_only=true&assignee_id=c-1`,
    )
  })
})

describe('my jobs', () => {
  it('groups jobs by what needs doing', () => {
    const waiting = summaryOfJob(job({ id: 'j-1' }))
    const active = summaryOfJob(accepted({ id: 'j-2', status: 'in_progress' }))
    const done = summaryOfJob(accepted({ id: 'j-3', status: 'completed' }))

    const groups = groupJobs([done, active, waiting])

    expect(groups.waiting.map((item) => item.id)).toEqual(['j-1'])
    expect(groups.active.map((item) => item.id)).toEqual(['j-2'])
    expect(groups.finished.map((item) => item.id)).toEqual(['j-3'])
  })

  it('lists the contractor’s jobs and links to each one', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs`]: {
        body: [
          summaryOfJob(job()),
          summaryOfJob(
            accepted({
              id: 'w-2',
              reference: 'WO-0002',
              title: 'Fix the gutter',
              status: 'in_progress',
              overdue: true,
            }),
          ),
        ],
      },
    })

    renderAt(`${ORG_PATH}/my-jobs`)

    const waiting = await screen.findByRole('region', { name: 'Waiting for your reply' })
    expect(within(waiting).getByRole('link', { name: /Replace kitchen tap/ })).toHaveAttribute(
      'href',
      `${ORG_PATH}/my-jobs/w-1`,
    )
    const hand = screen.getByRole('region', { name: 'In hand' })
    expect(within(hand).getByText('Overdue')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Finished' })).not.toBeInTheDocument()
  })

  it('explains an empty list', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs`]: { body: [] },
    })

    renderAt(`${ORG_PATH}/my-jobs`)

    expect(await screen.findByText(/You have no jobs right now/)).toBeInTheDocument()
  })
})

describe('a job', () => {
  it('holds back the resident and entry instructions until the job is accepted', async () => {
    let current = job()
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: () => ({ body: current }),
      [`POST ${ORG}/my-jobs/w-1/accept`]: () => {
        current = accepted()
        return { body: current }
      },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)

    expect(await screen.findByRole('heading', { name: 'Replace kitchen tap' })).toBeInTheDocument()
    expect(screen.getByText(/12 Maple Street, Springfield, IL 62701/)).toBeInTheDocument()
    expect(screen.queryByText('Ring the bell, I work from home')).not.toBeInTheDocument()
    expect(screen.getByText(/appear once you accept the job/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Add an update' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start work' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Accept job' }))

    expect(await screen.findByText('Ring the bell, I work from home')).toBeInTheDocument()
    expect(screen.getByText('Rae')).toBeInTheDocument()
    expect(screen.queryByText(/appear once you accept the job/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start work' })).toBeInTheDocument()
    expect(requests.some((request) => request.path === `${ORG}/my-jobs/w-1/accept`)).toBe(true)
  })

  it('never asks for or shows a phone number or email', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: { body: accepted() },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)

    await screen.findByRole('heading', { name: 'Replace kitchen tap' })
    expect(document.body).not.toHaveTextContent(/@|555-/)
    expect(screen.getByText(/go through the property team/)).toBeInTheDocument()
  })

  it('declines with a reason and returns to the list', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: { body: job() },
      [`GET ${ORG}/my-jobs`]: { body: [] },
      [`POST ${ORG}/my-jobs/w-1/decline`]: { status: 204 },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Decline' }))
    const form = screen.getByRole('form', { name: 'Decline the job' })

    fireEvent.click(within(form).getByRole('button', { name: 'Decline job' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'Say why you cannot take this job.',
    )
    expect(requests.some((request) => request.method === 'POST')).toBe(false)

    fireEvent.change(within(form).getByLabelText('Why can you not take it?'), {
      target: { value: 'Fully booked this week' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Decline job' }))

    expect(await screen.findByRole('heading', { name: 'My jobs' })).toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      reason: 'Fully booked this week',
    })
  })

  it('starts the job in one tap', async () => {
    let current = accepted()
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: () => ({ body: current }),
      [`POST ${ORG}/my-jobs/w-1/status`]: () => {
        current = accepted({
          status: 'in_progress',
          allowed_statuses: ['on_hold', 'ready_for_review'],
        })
        return { body: current }
      },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Start work' }))

    expect(await screen.findByRole('button', { name: 'Mark ready for review' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Put on hold' })).toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      status: 'in_progress',
      note: null,
    })
  })

  it.each([
    ['Put on hold', 'Why is the job on hold?', 'Confirm on hold', 'on_hold', 'Part on order'],
    [
      'Mark ready for review',
      'What was done?',
      'Confirm ready for review',
      'ready_for_review',
      'Fitted a new cartridge',
    ],
  ])('asks for words before %s', async (button, question, confirm, status, text) => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: {
        body: accepted({
          status: 'in_progress',
          allowed_statuses: ['on_hold', 'ready_for_review'],
        }),
      },
      [`POST ${ORG}/my-jobs/w-1/status`]: { body: accepted({ status: 'in_progress' }) },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: button }))
    const form = screen.getByRole('form', { name: confirm })

    fireEvent.click(within(form).getByRole('button', { name: confirm }))
    expect(await within(form).findByRole('alert')).toHaveTextContent(question)
    expect(requests.some((request) => request.method === 'POST')).toBe(false)

    fireEvent.change(within(form).getByLabelText(question), { target: { value: text } })
    fireEvent.click(within(form).getByRole('button', { name: confirm }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      status,
      note: text,
    })
  })

  it('resumes a job that is on hold', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: {
        body: accepted({ status: 'on_hold', allowed_statuses: ['in_progress'] }),
      },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)

    expect(await screen.findByRole('button', { name: 'Resume work' })).toBeInTheDocument()
  })

  it('sends a progress update, a note, or a question', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: {
        body: accepted({ status: 'in_progress', allowed_statuses: [] }),
      },
      [`POST ${ORG}/my-jobs/w-1/entries`]: { status: 201, body: accepted() },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)
    const form = await screen.findByRole('form', { name: 'Add an update' })

    fireEvent.click(within(form).getByRole('button', { name: 'Send update' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Write something first.')

    fireEvent.change(within(form).getByLabelText('Message'), { target: { value: 'Half done' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Send update' }))
    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))

    fireEvent.change(within(form).getByLabelText('Kind of update'), {
      target: { value: 'clarification' },
    })
    fireEvent.change(within(form).getByLabelText('Message'), {
      target: { value: 'Is the cabinet in scope?' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Send update' }))
    await waitFor(() =>
      expect(requests.filter((request) => request.method === 'POST')).toHaveLength(2),
    )

    expect(
      requests.filter((request) => request.method === 'POST').map((request) => request.body),
    ).toEqual([
      { body: 'Half done', kind: 'progress' },
      { body: 'Is the cabinet in scope?', kind: 'clarification' },
    ])
  })

  it('uploads a photo of the finished work', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: {
        body: accepted({
          status: 'in_progress',
          attachments: [
            {
              id: 'f-1',
              filename: 'before.png',
              content_type: 'image/png',
              size_bytes: 2048,
              mine: true,
              created_at: '2026-11-10T10:00:00Z',
            },
          ],
        }),
      },
      [`POST ${ORG}/my-jobs/w-1/attachments?filename=after.png`]: { status: 201, body: {} },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)
    const form = await screen.findByRole('form', { name: 'Attach a file' })
    expect(screen.getByRole('list', { name: 'Files' })).toHaveTextContent('Yours')
    expect(within(form).queryByLabelText('Share with the contractor')).not.toBeInTheDocument()

    fireEvent.click(within(form).getByRole('button', { name: 'Upload' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('Choose a file first.')

    fireEvent.change(within(form).getByLabelText('Add a photo of the work'), {
      target: { files: [new File(['x'], 'after.png', { type: 'image/png' })] },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Upload' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.path).toBe(
      `${ORG}/my-jobs/w-1/attachments?filename=after.png`,
    )
  })

  it('shows the history without anything internal, and is read-only once finished', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: {
        body: accepted({
          status: 'completed',
          allowed_statuses: [],
          timeline: [
            {
              id: 'e-1',
              kind: 'status_changed',
              body: null,
              status: 'completed',
              author: 'Property team',
              created_at: '2026-11-10T10:00:00Z',
            },
            {
              id: 'e-2',
              kind: 'progress',
              body: 'All done',
              status: null,
              author: 'You',
              created_at: '2026-11-10T09:00:00Z',
            },
          ],
        }),
      },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)

    const timeline = await screen.findByRole('list', { name: 'Job history' })
    expect(timeline).toHaveTextContent('Status changed to Completed')
    expect(timeline).toHaveTextContent('Property team')
    expect(timeline).toHaveTextContent('All done')
    expect(screen.queryByRole('form', { name: 'Add an update' })).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Attach a file' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Update the job' })).not.toBeInTheDocument()
  })

  it('treats another contractor’s job as missing', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-9`]: { status: 404, body: { detail: 'Job not found' } },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-9`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('shows a refusal from the server', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asContractor]) },
      [`GET ${ORG}/my-jobs/w-1`]: { body: accepted() },
      [`POST ${ORG}/my-jobs/w-1/status`]: {
        status: 409,
        body: { detail: 'You cannot move this job from assigned to in_progress' },
      },
    })

    renderAt(`${ORG_PATH}/my-jobs/w-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Start work' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('You cannot move this job')
  })
})
