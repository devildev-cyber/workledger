import { describe, expect, it } from 'vitest'

import { centsToInput, formatMoney, parseMoneyToCents } from './money.ts'

describe('parseMoneyToCents', () => {
  it.each([
    ['500', 50000],
    ['500.5', 50050],
    ['500.05', 50005],
    ['1,250.00', 125000],
    ['  75 ', 7500],
    ['0', 0],
  ])('reads %j as %i cents', (text, cents) => {
    expect(parseMoneyToCents(text)).toBe(cents)
  })

  it.each(['', 'abc', '-5', '5.123', '$5', '1.2.3'])('refuses %j', (text) => {
    expect(parseMoneyToCents(text)).toBeNull()
  })
})

describe('centsToInput', () => {
  it('round-trips with the parser', () => {
    expect(centsToInput(50050)).toBe('500.50')
    expect(parseMoneyToCents(centsToInput(50050))).toBe(50050)
    expect(centsToInput(null)).toBe('')
  })
})

describe('formatMoney', () => {
  it('shows the amount with its currency', () => {
    expect(formatMoney(50000, 'USD')).toContain('500.00')
  })

  it('falls back to plain text for an unknown currency', () => {
    expect(formatMoney(50000, '??')).toBe('500.00 ??')
  })
})
