import type { ReactNode } from 'react'

/** The centered card used by every page that is shown before someone is signed in. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow">
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {children}
      </div>
    </main>
  )
}
