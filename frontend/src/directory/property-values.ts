export type PropertyValues = {
  name: string
  street: string
  city: string
  region: string
  postal_code: string
  currency: string
  approval_threshold_cents: number | null
}

export const EMPTY_PROPERTY: PropertyValues = {
  name: '',
  street: '',
  city: '',
  region: '',
  postal_code: '',
  currency: 'USD',
  approval_threshold_cents: null,
}
