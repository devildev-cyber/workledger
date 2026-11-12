import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setCsrfToken, setUnauthorizedHandler } from './api/client.ts'
import type { ManagerChoice, Membership, MyHome, Property, Resident, Tenancy, Unit } from './api/types.ts'
import { HARBOR, harborAdmin, mockApi, sessionFor } from './test/fetch-mock.ts'
import { renderAt } from './test/render.tsx'

const ORG = `/api/organizations/${HARBOR.id}`
const MAPLE_ID = 'p-maple'
const MAPLE = `${ORG}/properties/${MAPLE_ID}`

const asManager: Membership = { ...harborAdmin, roles: ['manager'] }
const asResident: Membership = { ...harborAdmin, roles: ['resident'] }

const maple: Property = {
  id: MAPLE_ID,
  name: 'Maple Court',
  street: '12 Maple Street',
  city: 'Springfield',
  region: 'IL',
  postal_code: '62701',
  currency: 'USD',
  approval_threshold_cents: 50000,
  unit_count: 2,
  buildings: [{ id: 'b-a', name: 'Building A' }],
}

const units: Unit[] = [
  {
    id: 'u-1',
    property_id: MAPLE_ID,
    building_id: 'b-a',
    label: '1A',
    current_residents: [{ id: 'r-rae', full_name: 'Rae Resident' }],
  },
  { id: 'u-2', property_id: MAPLE_ID, building_id: null, label: '2B', current_residents: [] },
]

function tenancy(id: string, moveOut: string | null): Tenancy {
  return {
    id,
    unit_id: 'u-1',
    unit_label: '1A',
    building_name: 'Building A',
    property_id: MAPLE_ID,
    property_name: 'Maple Court',
    move_in_date: '2026-03-01',
    move_out_date: moveOut,
    is_current: moveOut === null,
  }
}

const rae: Resident = {
  id: 'r-rae',
  full_name: 'Rae Resident',
  email: 'rae@example.com',
  phone: '555-0100',
  access_instructions: 'Gate code on file',
  has_account: true,
  tenancies: [tenancy('t-1', null)],
}

const sam: Resident = {
  id: 'r-sam',
  full_name: 'Sam Stayer',
  email: null,
  phone: null,
  access_instructions: null,
  has_account: false,
  tenancies: [],
}

beforeEach(() => {
  localStorage.clear()
  setCsrfToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('navigation by role', () => {
  it('shows administrators the directory links', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([harborAdmin]) } })

    renderAt(`/organizations/${HARBOR.id}`)

    expect(await screen.findByRole('link', { name: 'Properties' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Residents' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'My home' })).not.toBeInTheDocument()
  })

  it('shows residents only their own home link', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asResident]) } })

    renderAt(`/organizations/${HARBOR.id}`)

    expect(await screen.findByRole('link', { name: 'My home' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Properties' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Residents' })).not.toBeInTheDocument()
  })

  it('keeps the directory pages away from residents', async () => {
    const { requests } = mockApi({ 'GET /api/auth/me': { body: sessionFor([asResident]) } })

    renderAt(`/organizations/${HARBOR.id}/residents`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(requests).toHaveLength(1)
  })
})

describe('properties list', () => {
  it('lists properties and links to each one', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/properties`]: { body: [maple] },
    })

    renderAt(`/organizations/${HARBOR.id}/properties`)

    const link = await screen.findByRole('link', { name: 'Maple Court' })
    expect(link).toHaveAttribute('href', `/organizations/${HARBOR.id}/properties/${MAPLE_ID}`)
    expect(screen.getByText('12 Maple Street, Springfield, IL 62701')).toBeInTheDocument()
    expect(screen.getByText('2 units')).toBeInTheDocument()
  })

  it('sends the approval threshold as whole cents and shows the new property', async () => {
    let created = false
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin], 'csrf-9') },
      [`GET ${ORG}/properties`]: () => ({ body: created ? [maple] : [] }),
      [`POST ${ORG}/properties`]: () => {
        created = true
        return { status: 201, body: maple }
      },
    })

    renderAt(`/organizations/${HARBOR.id}/properties`)
    expect(await screen.findByText(/No properties yet/)).toBeInTheDocument()

    const form = screen.getByRole('form', { name: 'Add property' })
    fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'Maple Court' } })
    fireEvent.change(within(form).getByLabelText('Approval threshold'), { target: { value: '1,250.50' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Add property' }))

    expect(await screen.findByRole('link', { name: 'Maple Court' })).toBeInTheDocument()
    const post = requests.find((request) => request.method === 'POST')
    expect(post?.body).toMatchObject({
      name: 'Maple Court',
      currency: 'USD',
      approval_threshold_cents: 125050,
    })
    expect(post?.headers['X-CSRF-Token']).toBe('csrf-9')
  })

  it('does not send a threshold that is not an amount', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/properties`]: { body: [] },
    })

    renderAt(`/organizations/${HARBOR.id}/properties`)
    const form = await screen.findByRole('form', { name: 'Add property' })
    fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'Maple Court' } })
    fireEvent.change(within(form).getByLabelText('Approval threshold'), { target: { value: 'lots' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Add property' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/amount/)
    expect(requests.some((request) => request.method === 'POST')).toBe(false)
  })

  it('shows the server message when the name is taken', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/properties`]: { body: [maple] },
      [`POST ${ORG}/properties`]: {
        status: 409,
        body: { detail: 'A property with this name already exists.' },
      },
    })

    renderAt(`/organizations/${HARBOR.id}/properties`)
    const form = await screen.findByRole('form', { name: 'Add property' })
    fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'Maple Court' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Add property' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A property with this name already exists.')
  })

  it('gives managers a read-only list', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: [maple] },
    })

    renderAt(`/organizations/${HARBOR.id}/properties`)

    expect(await screen.findByRole('link', { name: 'Maple Court' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Add property' })).not.toBeInTheDocument()
  })

  it('tells a manager with no assignments to ask an administrator', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/properties`]: { body: [] },
    })

    renderAt(`/organizations/${HARBOR.id}/properties`)

    expect(await screen.findByText(/No properties are assigned to you yet/)).toBeInTheDocument()
  })
})

describe('property page', () => {
  const managerChoices: ManagerChoice[] = [
    { membership_id: 'm-mo', full_name: 'Mo Manager', email: 'mo@example.com', assigned: true },
    { membership_id: 'm-di', full_name: 'Di Manager', email: 'di@example.com', assigned: false },
  ]

  it('shows details, units with their residents, and vacancies', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${MAPLE}`]: { body: maple },
      [`GET ${MAPLE}/units`]: { body: units },
      [`GET ${MAPLE}/managers`]: { body: managerChoices },
    })

    renderAt(`/organizations/${HARBOR.id}/properties/${MAPLE_ID}`)

    expect(await screen.findByRole('heading', { name: 'Maple Court' })).toBeInTheDocument()
    expect(screen.getByText(/500\.00/)).toBeInTheDocument()
    expect(await screen.findByText('Building A · 1A')).toBeInTheDocument()
    expect(screen.getByText('Rae Resident')).toBeInTheDocument()
    expect(screen.getByText('Vacant')).toBeInTheDocument()
  })

  it('adds a unit to a building', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${MAPLE}`]: { body: maple },
      [`GET ${MAPLE}/units`]: { body: units },
      [`GET ${MAPLE}/managers`]: { body: managerChoices },
      [`POST ${MAPLE}/units`]: { status: 201, body: units[0] },
    })

    renderAt(`/organizations/${HARBOR.id}/properties/${MAPLE_ID}`)
    const form = await screen.findByRole('form', { name: 'Add unit' })
    fireEvent.change(within(form).getByLabelText('Unit'), { target: { value: '3C' } })
    fireEvent.change(within(form).getByLabelText('Building'), { target: { value: 'b-a' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Add unit' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      label: '3C',
      building_id: 'b-a',
    })
  })

  it('saves the chosen managers', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${MAPLE}`]: { body: maple },
      [`GET ${MAPLE}/units`]: { body: units },
      [`GET ${MAPLE}/managers`]: { body: managerChoices },
      [`PUT ${MAPLE}/managers`]: { body: managerChoices },
    })

    renderAt(`/organizations/${HARBOR.id}/properties/${MAPLE_ID}`)
    expect(await screen.findByLabelText(/Mo Manager/)).toBeChecked()
    fireEvent.click(screen.getByLabelText(/Di Manager/))
    fireEvent.click(screen.getByRole('button', { name: 'Save managers' }))

    expect(await screen.findByText('Managers saved.')).toBeInTheDocument()
    const put = requests.find((request) => request.method === 'PUT')
    expect(put?.body).toEqual({ membership_ids: ['m-mo', 'm-di'] })
  })

  it('shows managers the property without any editing tools', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${MAPLE}`]: { body: maple },
      [`GET ${MAPLE}/units`]: { body: units },
    })

    renderAt(`/organizations/${HARBOR.id}/properties/${MAPLE_ID}`)

    expect(await screen.findByRole('heading', { name: 'Maple Court' })).toBeInTheDocument()
    expect(await screen.findByText('Building A · 1A')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Add unit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Managers' })).not.toBeInTheDocument()
    expect(requests.some((request) => request.path.endsWith('/managers'))).toBe(false)
  })

  it('shows not found for a property the person cannot see', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${MAPLE}`]: { status: 404, body: { detail: 'Not found' } },
      [`GET ${MAPLE}/units`]: { status: 404, body: { detail: 'Not found' } },
    })

    renderAt(`/organizations/${HARBOR.id}/properties/${MAPLE_ID}`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('edits the details', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${MAPLE}`]: { body: maple },
      [`GET ${MAPLE}/units`]: { body: units },
      [`GET ${MAPLE}/managers`]: { body: managerChoices },
      [`PUT ${MAPLE}`]: { body: maple },
    })

    renderAt(`/organizations/${HARBOR.id}/properties/${MAPLE_ID}`)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit details' }))
    const form = screen.getByRole('form', { name: 'Edit property' })
    expect(within(form).getByLabelText('Approval threshold')).toHaveValue('500.00')
    fireEvent.change(within(form).getByLabelText('Approval threshold'), { target: { value: '750' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(screen.queryByRole('form', { name: 'Edit property' })).not.toBeInTheDocument())
    expect(requests.find((request) => request.method === 'PUT')?.body).toMatchObject({
      name: 'Maple Court',
      approval_threshold_cents: 75000,
    })
  })
})

describe('residents page', () => {
  it('shows contact details, account status and placements', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/residents`]: { body: [rae, sam] },
      [`GET ${ORG}/properties`]: { body: [maple] },
    })

    renderAt(`/organizations/${HARBOR.id}/residents`)

    expect(await screen.findByRole('heading', { name: 'Rae Resident' })).toBeInTheDocument()
    expect(screen.getByText('rae@example.com')).toBeInTheDocument()
    expect(screen.getByText('555-0100')).toBeInTheDocument()
    expect(screen.getByText('Has account')).toBeInTheDocument()
    expect(screen.getByText('Building A · 1A, Maple Court')).toBeInTheDocument()
    expect(screen.getByText('Not placed in any unit.')).toBeInTheDocument()
  })

  it('adds a resident', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/residents`]: { body: [] },
      [`GET ${ORG}/properties`]: { body: [] },
      [`POST ${ORG}/residents`]: { status: 201, body: rae },
    })

    renderAt(`/organizations/${HARBOR.id}/residents`)
    const form = await screen.findByRole('form', { name: 'Add resident' })
    fireEvent.change(within(form).getByLabelText('Full name'), { target: { value: 'Rae Resident' } })
    fireEvent.change(within(form).getByLabelText('Email'), { target: { value: 'rae@example.com' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Add resident' }))

    await waitFor(() => expect(requests.some((request) => request.method === 'POST')).toBe(true))
    expect(requests.find((request) => request.method === 'POST')?.body).toMatchObject({
      full_name: 'Rae Resident',
      email: 'rae@example.com',
    })
  })

  it('moves a resident into a unit of the chosen property', async () => {
    const { requests } = mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/residents`]: { body: [sam] },
      [`GET ${ORG}/properties`]: { body: [maple] },
      [`GET ${MAPLE}/units`]: { body: units },
      [`POST ${ORG}/tenancies`]: { status: 201, body: tenancy('t-new', null) },
    })

    renderAt(`/organizations/${HARBOR.id}/residents`)
    fireEvent.click(await screen.findByRole('button', { name: 'Move in Sam Stayer' }))
    const form = await screen.findByRole('form', { name: 'Move in Sam Stayer' })

    expect(within(form).getByLabelText('Unit')).toBeDisabled()
    fireEvent.change(within(form).getByLabelText('Property'), { target: { value: MAPLE_ID } })
    await within(form).findByRole('option', { name: '2B' })
    fireEvent.change(within(form).getByLabelText('Unit'), { target: { value: 'u-2' } })
    fireEvent.change(within(form).getByLabelText('Move-in date'), { target: { value: '2026-11-15' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Move in' }))

    await waitFor(() => expect(screen.queryByRole('form', { name: 'Move in Sam Stayer' })).not.toBeInTheDocument())
    expect(requests.find((request) => request.method === 'POST')?.body).toEqual({
      unit_id: 'u-2',
      resident_id: 'r-sam',
      move_in_date: '2026-11-15',
    })
  })

  it('records a move-out and shows a conflict message from the server', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([harborAdmin]) },
      [`GET ${ORG}/residents`]: { body: [rae] },
      [`GET ${ORG}/properties`]: { body: [maple] },
      [`POST ${ORG}/tenancies/t-1/end`]: {
        status: 409,
        body: { detail: 'The move-out date cannot be before the move-in date.' },
      },
    })

    renderAt(`/organizations/${HARBOR.id}/residents`)
    fireEvent.click(await screen.findByRole('button', { name: /Record move-out from/ }))
    const form = screen.getByRole('form', { name: /Move out from/ })
    fireEvent.change(within(form).getByLabelText('Move-out date'), { target: { value: '2026-01-01' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save move-out' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('cannot be before the move-in date')
  })

  it('lets managers read the directory but not change it', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asManager]) },
      [`GET ${ORG}/residents`]: { body: [rae] },
      [`GET ${ORG}/properties`]: { body: [maple] },
    })

    renderAt(`/organizations/${HARBOR.id}/residents`)

    expect(await screen.findByText('555-0100')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Add resident' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Move in/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Record move-out/ })).not.toBeInTheDocument()
  })
})

describe('my home', () => {
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

  it('shows the resident their own homes', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-home`]: { body: [home] },
    })

    renderAt(`/organizations/${HARBOR.id}/my-home`)

    expect(await screen.findByRole('heading', { name: 'Building A · 1A, Maple Court' })).toBeInTheDocument()
    expect(screen.getByText('12 Maple Street, Springfield, IL 62701')).toBeInTheDocument()
    expect(screen.getByText(/Moved in/)).toBeInTheDocument()
  })

  it('explains what to do when no home is linked', async () => {
    mockApi({
      'GET /api/auth/me': { body: sessionFor([asResident]) },
      [`GET ${ORG}/my-home`]: { body: [] },
    })

    renderAt(`/organizations/${HARBOR.id}/my-home`)

    expect(await screen.findByText(/Contact your property manager/)).toBeInTheDocument()
  })

  it('is not available to staff roles without the resident role', async () => {
    mockApi({ 'GET /api/auth/me': { body: sessionFor([asManager]) } })

    renderAt(`/organizations/${HARBOR.id}/my-home`)

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
