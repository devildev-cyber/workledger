export function FormError({ message }: { message: string | null }) {
  if (!message) {
    return null
  }

  return (
    <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
      {message}
    </p>
  )
}
