import type { ReactNode } from 'react'

/** One labelled number in a report. */
export function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="text-xl font-semibold">{value}</dd>
    </div>
  )
}

export function Figures({ children }: { children: ReactNode }) {
  return <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</dl>
}
