import type { ComponentProps } from 'react'

type TextAreaFieldProps = Omit<ComponentProps<'textarea'>, 'onChange' | 'value'> & {
  label: string
  value: string
  onChange: (value: string) => void
}

export function TextAreaField({ label, id, onChange, ...textareaProps }: TextAreaFieldProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <textarea
        id={id}
        rows={4}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded border border-slate-300 px-3 py-2"
        {...textareaProps}
      />
    </div>
  )
}
