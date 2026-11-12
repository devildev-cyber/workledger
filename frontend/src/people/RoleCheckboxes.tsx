import type { Role } from '../api/types.ts'
import { roleLabel } from '../organizations/organizations.ts'

type RoleCheckboxesProps = {
  legend: string
  options: Role[]
  selected: Role[]
  onChange: (roles: Role[]) => void
}

export function RoleCheckboxes({ legend, options, selected, onChange }: RoleCheckboxesProps) {
  const toggle = (role: Role, checked: boolean) => {
    onChange(checked ? [...selected, role] : selected.filter((item) => item !== role))
  }

  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium text-slate-700">{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {options.map((role) => (
          <label key={role} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(role)}
              onChange={(event) => toggle(role, event.target.checked)}
            />
            {roleLabel(role)}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
