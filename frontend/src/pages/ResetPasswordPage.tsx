import { useState, type SubmitEventHandler } from 'react'
import { Link } from 'react-router'

import { api, ApiError } from '../api/client.ts'
import { useAuth } from '../auth/auth-context.ts'
import { useLinkToken } from '../auth/link-token.ts'
import { passwordProblem } from '../auth/password.ts'
import { AuthCard } from '../components/AuthCard.tsx'
import { FormError } from '../components/FormError.tsx'
import { NewPasswordFields } from '../components/NewPasswordFields.tsx'

export function ResetPasswordPage() {
  const token = useLinkToken()
  const { state, setSession } = useAuth()
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  if (!token) {
    return (
      <AuthCard title="Reset link not valid">
        <p className="text-slate-700">
          This reset link is incomplete. Open the link from your email again, or ask for a new one.
        </p>
        <Link to="/forgot-password" className="text-sm text-slate-700 underline">
          Send a new reset link
        </Link>
      </AuthCard>
    )
  }

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    const problem = passwordProblem(password, confirmation)
    if (problem) {
      setError(problem)
      return
    }

    setError(null)
    setSubmitting(true)
    try {
      await api('/auth/password-reset/confirm', { method: 'POST', body: { token, password } })
      // The server ends every session of this account, including one in this browser.
      if (state.status === 'signed-in') setSession(null)
      setDone(true)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <AuthCard title="Password changed">
        <p role="status" className="text-slate-700">
          Your password has been changed. You have been signed out everywhere, so sign in again
          with the new password.
        </p>
        <Link to="/sign-in" className="inline-block rounded bg-slate-900 px-4 py-2 text-white">
          Go to sign in
        </Link>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Choose a new password">
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />
        <NewPasswordFields
          password={password}
          confirmation={confirmation}
          onPasswordChange={setPassword}
          onConfirmationChange={setConfirmation}
        />
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {submitting ? 'Saving…' : 'Change password'}
        </button>
      </form>
      {error && (
        <Link to="/forgot-password" className="text-sm text-slate-700 underline">
          Send a new reset link
        </Link>
      )}
    </AuthCard>
  )
}
