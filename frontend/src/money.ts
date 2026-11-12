/** Amounts are whole cents everywhere in the API, so they never pass through floating point. */

export function formatMoney(cents: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(cents / 100)
  } catch {
    // An unknown currency code is shown plainly rather than breaking the page.
    return `${(cents / 100).toFixed(2)} ${currency}`
  }
}

/** "500", "500.5" and "1,250.00" become cents. Anything else gives null. */
export function parseMoneyToCents(text: string): number | null {
  const cleaned = text.trim().replace(/,/g, '')
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
    return null
  }
  const [whole, fraction = ''] = cleaned.split('.')
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
}

export function centsToInput(cents: number | null): string {
  return cents === null ? '' : (cents / 100).toFixed(2)
}
