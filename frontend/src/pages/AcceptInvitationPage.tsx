import { useEffect, useState, type SubmitEventHandler } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { api, ApiError } from '../api/client.ts'
import type { InvitationPreview, SessionResponse } from '../api/types.ts'
import { useAuth } from '../auth/auth-context.ts'
import { useLinkToken } from '../auth/link-token.ts'
import { passwordProblem } from '../auth/password.ts'
import { AuthCard } from '../components/AuthCard.tsx'
import { FormError } from '../components/FormError.tsx'
import { NewPasswordFields } from '../components/NewPasswordFields.tsx'
import { TextField } from '../components/TextField.tsx'
import { organizationPath, roleLabel } from '../organizations/organizations.ts'

type PreviewResult =
  | { token: string; status: 'ready'; preview: InvitationPreview }
  | { token: string; status: 'invalid'; message: string }

function messageFor(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
}

export function AcceptInvitationPage() {
  const token = useLinkToken()
  const { state, setSession, signOut } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [result, setResult] = useState<PreviewResult | null>(null)
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!token) return
    let cancelled = false

    api<InvitationPreview>('/invitations/preview', { method: 'POST', body: { token } })
      .then((preview) => {
        if (!cancelled) setResult({ token, status: 'ready', preview })
      })
      .catch((caught: unknown) => {
        if (!cancelled) setResult({ token, status: 'invalid', message: messageFor(caught) })
      })

    return () => {
      cancelled = true
    }
  }, [token])

  if (!token) {
    return (
      <AuthCard title="Invitation not valid">
        <p className="text-slate-700">
          This invitation link is incomplete. Open the link from your email again.
        </p>
      </AuthCard>
    )
  }

  if (state.status === 'loading' || result?.token !== token) {
    return (
      <AuthCard title="Invitation">
        <p role="status" className="text-slate-600">
          Loading…
        </p>
      </AuthCard>
    )
  }

  if (result.status === 'invalid') {
    return (
      <AuthCard title="Invitation not valid">
        <p className="text-slate-700">{result.message}</p>
        <Link to="/sign-in" className="text-sm text-slate-700 underline">
          Go to sign in
        </Link>
      </AuthCard>
    )
  }

  const { preview } = result
  const roles = preview.roles.map(roleLabel).join(', ')

  const accept = async (body: Record<string, string>) => {
    setError(null)
    setSubmitting(true)
    try {
      const session = await api<SessionResponse>('/invitations/accept', {
        method: 'POST',
        body: { token, ...body },
      })
      setSession(session)
      navigate(organizationPath(preview.organization_id), { replace: true })
    } catch (caught) {
      setError(messageFor(caught))
      setSubmitting(false)
    }
  }

  const handleCreateAccount: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    const problem = passwordProblem(password, confirmation)
    if (problem) {
      setError(problem)
      return
    }
    void accept({ full_name: fullName.trim(), password })
  }

  const intro = (
    <p className="text-slate-700">
      You have been invited to join <strong>{preview.organization_name}</strong> as {roles}. This
      invitation is for {preview.email}.
    </p>
  )

  // Someone with an account must prove it is theirs by being signed in to it.
  if (preview.has_account) {
    if (state.status !== 'signed-in') {
      const from = `${location.pathname}${location.search}${location.hash}`
      return (
        <AuthCard title="Join an organization">
          {intro}
          <p className="text-slate-700">Sign in to your account to accept it.</p>
          <Link
            to="/sign-in"
            state={{ from }}
            className="inline-block rounded bg-slate-900 px-4 py-2 text-white"
          >
            Sign in
          </Link>
        </AuthCard>
      )
    }

    if (state.user.email.toLowerCase() !== preview.email.toLowerCase()) {
      return (
        <AuthCard title="Join an organization">
          {intro}
          <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
            You are signed in as {state.user.email}. Sign out and sign in as {preview.email} to
            accept this invitation.
          </p>
          <button
            type="button"
            onClick={() => void signOut()}
            className="rounded border border-slate-300 px-4 py-2"
          >
            Sign out
          </button>
        </AuthCard>
      )
    }

    return (
      <AuthCard title="Join an organization">
        {intro}
        <FormError message={error} />
        <button
          type="button"
          disabled={submitting}
          onClick={() => void accept({})}
          className="w-full rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {submitting ? 'Joining…' : 'Accept invitation'}
        </button>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Create your account">
      {intro}
      <form onSubmit={handleCreateAccount} className="space-y-4">
        <FormError message={error} />
        <TextField
          id="full-name"
          label="Full name"
          autoComplete="name"
          required
          maxLength={200}
          value={fullName}
          onChange={setFullName}
        />
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
          {submitting ? 'Creating account…' : 'Create account and join'}
        </button>
      </form>
    </AuthCard>
  )
}
