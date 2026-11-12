import { Route, Routes } from 'react-router'

import { AuthProvider } from './auth/AuthProvider.tsx'
import { RequireAuth } from './auth/RequireAuth.tsx'
import { AppShell } from './layout/AppShell.tsx'
import { HomeRedirect } from './pages/HomeRedirect.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { OrganizationHomePage } from './pages/OrganizationHomePage.tsx'
import { SignInPage } from './pages/SignInPage.tsx'

// The router itself is supplied by main.tsx, so tests can start at any address.
function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<HomeRedirect />} />
            <Route path="organizations/:organizationId" element={<OrganizationHomePage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
