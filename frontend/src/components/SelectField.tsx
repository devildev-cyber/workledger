import type { ComponentProps } from 'react'

type SelectFieldProps = Omit<ComponentProps<'select'>, 'onChange' | 'value'> & {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
  placeholder?: string
}

export function SelectField({
  label,
  id,
  options,
  placeholder,
  onChange,
  ...selectProps
}: SelectFieldProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <select
        id={id}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded border border-slate-300 bg-white px-3 py-2"
        {...selectProps}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
