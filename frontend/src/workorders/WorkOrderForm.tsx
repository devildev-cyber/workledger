import { useState, type SubmitEventHandler } from 'react'

import type { RequestCategory, Urgency } from '../api/types.ts'
import { useAction } from '../api/useAction.ts'
import { FormError } from '../components/FormError.tsx'
import { SelectField } from '../components/SelectField.tsx'
import { TextAreaField } from '../components/TextAreaField.tsx'
import { TextField } from '../components/TextField.tsx'
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  URGENCY_ORDER,
  URGENCY_SHORT,
} from '../requests/labels.ts'

export type WorkOrderValues = {
  title: string
  scope: string
  category: RequestCategory
  priority: Urgency
  due_date: string | null
}

type WorkOrderFormProps = {
  label: string
  submitLabel: string
  initial: WorkOrderValues
  // Standalone work orders choose a property. Edits and conversions already have one.
  properties?: { id: string; name: string }[]
  onSubmit: (values: WorkOrderValues, propertyId: string) => Promise<unknown>
  onCancel?: () => void
}

export function WorkOrderForm({
  label,
  submitLabel,
  initial,
  properties,
  onSubmit,
  onCancel,
}: WorkOrderFormProps) {
  const [title, setTitle] = useState(initial.title)
  const [scope, setScope] = useState(initial.scope)
  const [category, setCategory] = useState<string>(initial.category)
  const [priority, setPriority] = useState<string>(initial.priority)
  const [dueDate, setDueDate] = useState(initial.due_date ?? '')
  const [propertyId, setPropertyId] = useState('')
  const { busy, error, run, fail } = useAction()

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (properties && propertyId === '') {
      fail('Choose a property.')
      return
    }
    if (title.trim().length < 3) {
      fail('Give the work order a title of at least 3 characters.')
      return
    }
    if (scope.trim() === '') {
      fail('Describe the work to be done.')
      return
    }
    await run(() =>
      onSubmit(
        {
          title: title.trim(),
          scope: scope.trim(),
          category: category as RequestCategory,
          priority: priority as Urgency,
          due_date: dueDate === '' ? null : dueDate,
        },
        propertyId,
      ),
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={label}
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      {properties && (
        <SelectField
          id="work-order-property"
          label="Property"
          placeholder="Choose a property"
          value={propertyId}
          options={properties.map((item) => ({ value: item.id, label: item.name }))}
          onChange={setPropertyId}
        />
      )}
      <TextField
        id="work-order-title"
        label="Title"
        maxLength={200}
        value={title}
        onChange={setTitle}
      />
      <TextAreaField
        id="work-order-scope"
        label="Scope of work"
        maxLength={5000}
        rows={4}
        value={scope}
        onChange={setScope}
      />
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectField
          id="work-order-category"
          label="Kind of work"
          value={category}
          options={CATEGORY_ORDER.map((value) => ({ value, label: CATEGORY_LABELS[value] }))}
          onChange={setCategory}
        />
        <SelectField
          id="work-order-priority"
          label="Priority"
          value={priority}
          options={URGENCY_ORDER.map((value) => ({ value, label: URGENCY_SHORT[value] }))}
          onChange={setPriority}
        />
        <TextField
          id="work-order-due"
          label="Due date"
          type="date"
          value={dueDate}
          onChange={setDueDate}
        />
      </div>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {submitLabel}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-300 px-4 py-2"
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
