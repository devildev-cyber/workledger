import type { ComponentProps } from 'react'

type TextFieldProps = Omit<ComponentProps<'input'>, 'onChange' | 'value'> & {
  label: string
  value: string
  onChange: (value: string) => void
}

export function TextField({ label, id, onChange, ...inputProps }: TextFieldProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded border border-slate-300 px-3 py-2"
        {...inputProps}
      />
    </div>
  )
}
