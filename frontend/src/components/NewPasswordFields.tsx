import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from '../auth/password.ts'
import { TextField } from './TextField.tsx'

type NewPasswordFieldsProps = {
  password: string
  confirmation: string
  onPasswordChange: (value: string) => void
  onConfirmationChange: (value: string) => void
}

export function NewPasswordFields(props: NewPasswordFieldsProps) {
  return (
    <>
      <TextField
        id="new-password"
        label="New password"
        type="password"
        autoComplete="new-password"
        required
        value={props.password}
        onChange={props.onPasswordChange}
        aria-describedby="new-password-hint"
      />
      <p id="new-password-hint" className="text-sm text-slate-600">
        Use {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters.
      </p>
      <TextField
        id="confirm-password"
        label="Confirm password"
        type="password"
        autoComplete="new-password"
        required
        value={props.confirmation}
        onChange={props.onConfirmationChange}
      />
    </>
  )
}
