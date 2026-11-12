import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type {
  Membership,
  MyHome,
  RequestStatus,
  ResidentRequest,
  StaffRequest,
  StaffRequestSummary,
} from './api/types.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const ORG_PATH = `/organizations/${HARBOR.id}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asResident: Membership = { ...harborAdmin, roles: ['resident'] }

const home: MyHome = {
  tenancy_id: 't-1',
  unit_id: 'u-1',
  property_name: 'Maple Court',
  street: '12 Maple Street',
  city: 'Springfield',
  region: 'IL',
  postal_code: '62701',
  building_name: 'Building A',
  unit_label: '1A',
  move_in_date: '2026-03-01',
  move_out_date: null,
}

function residentRequest(overrides: Partial<ResidentRequest> = {}): ResidentRequest {
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
    description: 'The cold tap has dripped all week.',
    location: 'Kitchen',
    access_notes: null,
    can_cancel: true,
    can_message: true,
    timeline: [
      {
        id: 'e-1',
        kind: 'submitted',
        body: null,
        status: 'submitted',
        created_at: '2026-11-10T10:00:00Z',
        author: 'You',
      },
    ],
    attachments: [],
    ...overrides,
  }
}

function staffRequest(overrides: Partial<StaffRequest> = {}): StaffRequest {
  return {
    ...residentRequest(),
    property_id: 'p-1',
    resident_name: 'Rae Resident',
    submitted_on_behalf: false,
    resident: {
      id: 'res-1',
      full_name: 'Rae Resident',
      email: 'rae@example.com',
      phone: '555-0111',
      access_instructions: 'Gate code on file',
      has_account: true,
    },
    timeline: [
      {
        id: 'e-1',
        kind: 'submitted',
        visibility: 'resident',
        body: null,
        status: 'submitted',
        created_at: '2026-11-10T10:00:00Z',
        author_name: 'Rae Resident',
      },
      {
        id: 'e-2',
        kind: 'note',
        visibility: 'internal',
        body: 'Check warranty first',
        status: null,
        created_at: '2026-11-11T10:00:00Z',
        author_name: 'Mo Manager',
      },
    ],
    attachments: [],
    ...overrides,
  } as StaffRequest
}

function summary(id: string, reference: string, status: RequestStatus): StaffRequestSummary {
  const { timeline, attachments, ...rest } = staffRequest({ id, reference, status })
  void timeline
  void attachments
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
  it('gives residents My requests and staff Requests', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asResident]) } })
    renderAt(ORG_PATH)
    expect(await screen.findByRole('link', { name: 'My requests' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Requests' })).not.toBeInTheDocument()
  })

  it('shows staff the Requests link', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asManager]) } })
    renderAt(ORG_PATH)
    expect(await screen.findByRole('link', { name: 'Requests' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'My requests' })).not.toBeInTheDocument()
  })

  it.each([
    ['resident', asResident, '/requests'],
    ['manager', asManager, '/my-requests'],
    ['resident', asResident, '/requests/r-1'],
  ])('keeps the %s away from %s', async (_name, membership, path) => {
    const { requests } = mockApi({ 'GET /api/auth/me': { body: sessionFor([membership]) } })
    renderAt(`${ORG_PATH}${path}`)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(requests).toHaveLength(1)
  })
})

describe('my requests', () => {
  it('lists requests with their status', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests`]: {
        body: [residentRequest(), residentRequest({ id: 'r-2', reference: 'REQ-0002', title: 'Light is out', status: 'in_progress' })],
      },
    })

    renderAt(`${ORG_PATH}/my-requests`)

    const link = await screen.findByRole('link', { name: 'Kitchen tap drips' })
    expect(link).toHaveAttribute('href', `${ORG_PATH}/my-requests/r-1`)
    expect(screen.getByText('Received')).toBeInTheDocument()
    expect(screen.getByText('In progress')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Report a problem' })).toHaveAttribute(
      'href',
      `${ORG_PATH}/my-requests/new`,
    )
  })

  it('invites a resident with no requests to report one', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests`]: { body: [] },
    })
    renderAt(`${ORG_PATH}/my-requests`)
    expect(await screen.findByText(/You have not reported anything yet/)).toBeInTheDocument()
  })
})

describe('reporting a problem', () => {
  function fillIn(form: HTMLElement) {
    fireEvent.change(within(form).getByLabelText('What kind of problem'), { target: { value: 'plumbing' } })
    fireEvent.change(within(form).getByLabelText('How urgent'), { target: { value: 'soon' } })
    fireEvent.change(within(form).getByLabelText('Short summary'), { target: { value: 'Kitchen tap drips' } })
    fireEvent.change(within(form).getByLabelText('What is happening'), {
      target: { value: 'The cold tap has dripped all week.' },
    })
    fireEvent.change(within(form).getByLabelText('Where in the home'), { target: { value: 'Kitchen' } })
  }

  it('sends the request and shows the reference as confirmation', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident], 'csrf-5') },
      [`GET ${ORG}/my-home`]: { body: [home] },
      [`POST ${ORG}/my-requests`]: { status: 201, body: residentRequest() },
      [`GET ${ORG}/my-requests/r-1`]: { body: residentRequest() },
    })

    renderAt(`${ORG_PATH}/my-requests/new`)
    const form = await screen.findByRole('form', { name: 'Report a problem' })
    expect(within(form).getByText(/Building A · 1A, Maple Court/)).toBeInTheDocument()
    fillIn(form)
    fireEvent.click(within(form).getByRole('button', { name: 'Send request' }))

    expect(await screen.findByText(/Request REQ-0001 received/)).toBeInTheDocument()
    const post = requests.find((request) => request.method === 'POST')
    expect(post?.body).toEqual({
      unit_id: 'u-1',
      category: 'plumbing',
      urgency: 'soon',
      title: 'Kitchen tap drips',
      description: 'The cold tap has dripped all week.',
      location: 'Kitchen',
      access_notes: '',
    })
    expect(post?.headers['X-CSRF-Token']).toBe('csrf-5')
  })

  it('lets a resident with several homes choose one', async () => {
    const second: MyHome = { ...home, unit_id: 'u-9', unit_label: '9Z', building_name: null }
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-home`]: { body: [home, second] },
      [`POST ${ORG}/my-requests`]: { status: 201, body: residentRequest() },
      [`GET ${ORG}/my-requests/r-1`]: { body: residentRequest() },
    })

    renderAt(`${ORG_PATH}/my-requests/new`)
    const form = await screen.findByRole('form', { name: 'Report a problem' })
    fireEvent.change(within(form).getByLabelText('Which home'), { target: { value: 'u-9' } })
    fillIn(form)
    fireEvent.click(within(form).getByRole('button', { name: 'Send request' }))

    await screen.findByText(/received/)
    expect(requests.find((request) => request.method === 'POST')?.body).toMatchObject({ unit_id: 'u-9' })
  })

  it('attaches files after the request is saved and reports any that fail', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-home`]: { body: [home] },
      [`POST ${ORG}/my-requests`]: { status: 201, body: residentRequest() },
      [`POST ${ORG}/my-requests/r-1/attachments?filename=leak.png`]: {
        status: 201,
        body: { id: 'a-1' },
      },
      [`POST ${ORG}/my-requests/r-1/attachments?filename=broken.pdf`]: {
        status: 422,
        body: { detail: 'Only JPEG, PNG, WebP images and PDF files can be attached' },
      },
      [`GET ${ORG}/my-requests/r-1`]: { body: residentRequest() },
    })

    renderAt(`${ORG_PATH}/my-requests/new`)
    const form = await screen.findByRole('form', { name: 'Report a problem' })
    fillIn(form)
    fireEvent.change(within(form).getByLabelText('Photos or PDFs'), {
      target: {
        files: [
          new File(['x'], 'leak.png', { type: 'image/png' }),
          new File(['x'], 'broken.pdf', { type: 'application/pdf' }),
        ],
      },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Send request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('could not be attached: broken.pdf')
    expect(screen.getByText(/Request REQ-0001 received/)).toBeInTheDocument()
    const uploads = requests.filter((request) => request.path.includes('/attachments'))
    expect(uploads.map((request) => request.path)).toEqual([
      `${ORG}/my-requests/r-1/attachments?filename=leak.png`,
      `${ORG}/my-requests/r-1/attachments?filename=broken.pdf`,
    ])
  })

  it('refuses unsuitable files before anything is sent', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-home`]: { body: [home] },
    })

    renderAt(`${ORG_PATH}/my-requests/new`)
    const form = await screen.findByRole('form', { name: 'Report a problem' })
    fillIn(form)
    fireEvent.change(within(form).getByLabelText('Photos or PDFs'), {
      target: { files: [new File(['x'], 'notes.txt', { type: 'text/plain' })] },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Send request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('notes.txt is not a JPEG')
    expect(requests.some((request) => request.method === 'POST')).toBe(false)
  })

  it('warns about danger when the urgency is emergency', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-home`]: { body: [home] },
    })
    renderAt(`${ORG_PATH}/my-requests/new`)
    const form = await screen.findByRole('form', { name: 'Report a problem' })

    fireEvent.change(within(form).getByLabelText('How urgent'), { target: { value: 'emergency' } })

    expect(within(form).getByRole('note')).toHaveTextContent(/call your local emergency number/)
  })

  it('explains what to do when no home is linked', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-home`]: { body: [] },
    })
    renderAt(`${ORG_PATH}/my-requests/new`)
    expect(await screen.findByText(/Contact your property manager/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Report a problem' })).not.toBeInTheDocument()
  })
})

describe('following a request', () => {
  it('shows the details and the progress', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests/r-1`]: {
        body: residentRequest({
          status: 'in_progress',
          timeline: [
            ...residentRequest().timeline,
            {
              id: 'e-2',
              kind: 'status_changed',
              body: null,
              status: 'in_progress',
              created_at: '2026-11-11T10:00:00Z',
              author: 'Property team',
            },
            {
              id: 'e-3',
              kind: 'message',
              body: 'A plumber is booked for Thursday.',
              status: null,
              created_at: '2026-11-11T10:05:00Z',
              author: 'Property team',
            },
          ],
          attachments: [
            { id: 'a-1', filename: 'leak.png', content_type: 'image/png', size_bytes: 2048, created_at: '2026-11-10T10:00:00Z' },
          ],
        }),
      },
    })

    renderAt(`${ORG_PATH}/my-requests/r-1`)

    expect(await screen.findByRole('heading', { name: 'Kitchen tap drips' })).toBeInTheDocument()
    const timeline = screen.getByRole('list', { name: 'Timeline' })
    expect(within(timeline).getByText('Request submitted')).toBeInTheDocument()
    expect(within(timeline).getByText('Status changed to In progress')).toBeInTheDocument()
    expect(within(timeline).getByText('A plumber is booked for Thursday.')).toBeInTheDocument()
    expect(screen.queryByText('Internal')).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'leak.png' })).toHaveAttribute(
      'src',
      `${ORG}/my-requests/r-1/attachments/a-1`,
    )
    expect(screen.queryByText(/received/)).not.toBeInTheDocument()
  })

  it('sends a message and reloads the timeline', async () => {
    let sent = false
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests/r-1`]: () => ({
        body: residentRequest({
          timeline: sent
            ? [
                ...residentRequest().timeline,
                { id: 'e-9', kind: 'message', body: 'Home after 5pm', status: null, created_at: '2026-11-11T10:00:00Z', author: 'You' },
              ]
            : residentRequest().timeline,
        }),
      }),
      [`POST ${ORG}/my-requests/r-1/messages`]: () => {
        sent = true
        return { status: 201, body: residentRequest() }
      },
    })

    renderAt(`${ORG_PATH}/my-requests/r-1`)
    const form = await screen.findByRole('form', { name: 'Send a message' })
    fireEvent.change(within(form).getByLabelText('Add a message'), { target: { value: 'Home after 5pm' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText('Home after 5pm', { selector: 'p' })).toBeInTheDocument()
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({ body: 'Home after 5pm' })
  })

  it('asks before withdrawing a request', async () => {
    let status: RequestStatus = 'submitted'
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests/r-1`]: () => ({
        body: residentRequest({ status, can_cancel: status === 'submitted', can_message: status === 'submitted' }),
      }),
      [`POST ${ORG}/my-requests/r-1/cancel`]: () => {
        status = 'cancelled'
        return { body: residentRequest({ status }) }
      },
    })

    renderAt(`${ORG_PATH}/my-requests/r-1`)
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw request' }))
    expect(requests.some((request) => request.method === 'POST')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Yes, withdraw' }))

    expect(await screen.findByText('Withdrawn')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Withdraw request' })).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Send a message' })).not.toBeInTheDocument()
  })

  it('hides withdrawing once work has started', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests/r-1`]: { body: residentRequest({ status: 'in_progress', can_cancel: false }) },
    })
    renderAt(`${ORG_PATH}/my-requests/r-1`)
    await screen.findByRole('heading', { name: 'Kitchen tap drips' })
    expect(screen.queryByRole('button', { name: 'Withdraw request' })).not.toBeInTheDocument()
  })

  it('shows not found for a request that is not theirs', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-requests/r-9`]: { status: 404, body: { detail: 'Request not found' } },
    })
    renderAt(`${ORG_PATH}/my-requests/r-9`)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})

describe('staff request list', () => {
  it('lists requests and filters by status', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests`]: { body: [summary('r-1', 'REQ-0001', 'submitted'), summary('r-2', 'REQ-0002', 'in_review')] },
      [`GET ${ORG}/requests?status=in_review`]: { body: [summary('r-2', 'REQ-0002', 'in_review')] },
    })

    renderAt(`${ORG_PATH}/requests`)

    expect(await screen.findByText('REQ-0001')).toBeInTheDocument()
    expect(screen.getByText('REQ-0002')).toBeInTheDocument()
    expect(screen.getAllByText('Rae Resident')).toHaveLength(2)

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'in_review' } })
    await waitFor(() => expect(screen.queryByText('REQ-0001')).not.toBeInTheDocument())
    expect(screen.getByText('REQ-0002')).toBeInTheDocument()
  })

  it('says so when nothing has been reported', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/requests`]: { body: [] },
    })
    renderAt(`${ORG_PATH}/requests`)
    expect(await screen.findByText('No requests have been reported yet.')).toBeInTheDocument()
  })
})

describe('staff request page', () => {
  it('shows the resident, internal notes and who can see each entry', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)

    expect(await screen.findByText('555-0111')).toBeInTheDocument()
    expect(screen.getByText('Gate code on file')).toBeInTheDocument()
    const timeline = screen.getByRole('list', { name: 'Timeline' })
    expect(within(timeline).getByText('Check warranty first')).toBeInTheDocument()
    expect(within(timeline).getByText('Internal')).toBeInTheDocument()
    expect(within(timeline).getByText(/Mo Manager/)).toBeInTheDocument()
  })

  it('saves a status change with a message for the resident', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
      [`POST ${ORG}/requests/r-1/updates`]: { status: 201, body: staffRequest() },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    const form = await screen.findByRole('form', { name: 'Update request' })
    fireEvent.change(within(form).getByLabelText('Change status'), { target: { value: 'in_review' } })
    fireEvent.change(within(form).getByLabelText('Note or message'), { target: { value: 'Looking into it' } })
    fireEvent.click(within(form).getByLabelText('Message the resident can read'))
    fireEvent.click(within(form).getByRole('button', { name: 'Save update' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      status: 'in_review',
      body: 'Looking into it',
      visibility: 'resident',
    })
  })

  it('keeps notes internal unless the manager chooses otherwise', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
      [`POST ${ORG}/requests/r-1/updates`]: { status: 201, body: staffRequest() },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    const form = await screen.findByRole('form', { name: 'Update request' })
    fireEvent.change(within(form).getByLabelText('Note or message'), { target: { value: 'Call vendor' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save update' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      status: null,
      body: 'Call vendor',
      visibility: 'internal',
    })
  })

  it('does not send an empty update', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    const form = await screen.findByRole('form', { name: 'Update request' })
    fireEvent.click(within(form).getByRole('button', { name: 'Save update' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Write a note or choose a new status.')
    expect(requests.some((request) => request.method === 'POST')).toBe(false)
  })

  it('shows the server message when the change is not allowed', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/requests/r-1`]: { body: staffRequest() },
      [`POST ${ORG}/requests/r-1/updates`]: {
        status: 409,
        body: { detail: 'The request already has this status' },
      },
    })

    renderAt(`${ORG_PATH}/requests/r-1`)
    const form = await screen.findByRole('form', { name: 'Update request' })
    fireEvent.change(within(form).getByLabelText('Change status'), { target: { value: 'in_review' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save update' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already has this status')
  })
})
