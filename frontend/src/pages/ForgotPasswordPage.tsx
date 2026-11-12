import { useState, type SubmitEventHandler } from 'react'
import { Link } from 'react-router'

import { api, ApiError } from '../api/client.ts'
import { AuthCard } from '../components/AuthCard.tsx'
import { FormError } from '../components/FormError.tsx'
import { TextField } from '../components/TextField.tsx'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [confirmation, setConfirmation] = useState<string | null>(null)

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const reply = await api<{ detail: string }>('/auth/password-reset/request', {
        method: 'POST',
        body: { email: email.trim() },
      })
      setConfirmation(reply.detail)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthCard title="Reset your password">
      {confirmation ? (
        // The server gives the same answer whether or not the address has an account.
        <p role="status" className="text-slate-700">
          {confirmation}
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <p className="text-sm text-slate-600">
            Enter your email address and we will send you a link to choose a new password.
          </p>
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
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            {submitting ? 'Sending…' : 'Send reset link'}
          </button>
        </form>
      )}

      <p className="text-sm">
        <Link to="/sign-in" className="text-slate-700 underline">
          Back to sign in
        </Link>
      </p>
    </AuthCard>
  )
}
