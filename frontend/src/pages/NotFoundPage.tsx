import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <section className="space-y-3">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-slate-600">
        This page does not exist, or you do not have access to it.
      </p>
      <Link to="/" className="text-slate-900 underline">
        Go to your home page
      </Link>
    </section>
  )
}
