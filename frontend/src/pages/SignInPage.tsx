import { useState, type SubmitEventHandler } from 'react'
import { Link, Navigate, useLocation } from 'react-router'

import { ApiError } from '../api/client.ts'
import { useAuth } from '../auth/auth-context.ts'
import { AuthCard } from '../components/AuthCard.tsx'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'

// Only follow paths inside this app, never a full address someone could have planted.
function safeDestination(value: unknown): string {
  if (typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')) {
    return value
  }
  return '/'
}

export function SignInPage() {
  const { state, signIn } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const destination = safeDestination((location.state as { from?: unknown } | null)?.from)

  if (state.status === 'signed-in') {
    return <Navigate to={destination} replace />
  }

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      await signIn(email.trim(), password)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  return (
    <AuthCard title="Sign in to WorkLedger">
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />

        <TextField
          id="email"
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={setEmail}
        />
        <TextField
          id="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={setPassword}
        />

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <p className="text-sm">
        <Link to="/forgot-password" className="text-slate-700 underline">
          Forgot your password?
        </Link>
      </p>
    </AuthCard>
  )
}
