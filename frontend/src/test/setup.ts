import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Slow machines, such as busy CI runners, can take longer than the 1 second default to
// render a screen for the first time. A generous limit costs nothing when tests pass.
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
})
