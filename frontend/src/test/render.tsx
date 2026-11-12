import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import App from '../App.tsx'

/** Renders the whole app as if the browser had opened this address. */
export function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}
