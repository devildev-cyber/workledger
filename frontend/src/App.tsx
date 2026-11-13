import { Route, Routes } from 'react-router'

import { ApprovalPage } from './pages/ApprovalPage.tsx'
import { ApprovalsPage } from './pages/ApprovalsPage.tsx'
import { AuthProvider } from './auth/AuthProvider.tsx'
import { RequireAuth } from './auth/RequireAuth.tsx'
import { AppShell } from './layout/AppShell.tsx'
import { AcceptInvitationPage } from './pages/AcceptInvitationPage.tsx'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage.tsx'
import { HelpPage } from './pages/HelpPage.tsx'
import { HomeRedirect } from './pages/HomeRedirect.tsx'
import { JobPage } from './pages/JobPage.tsx'
import { MyHomePage } from './pages/MyHomePage.tsx'
import { MyJobsPage } from './pages/MyJobsPage.tsx'
import { MyRequestPage } from './pages/MyRequestPage.tsx'
import { MyRequestsPage } from './pages/MyRequestsPage.tsx'
import { NewRequestPage } from './pages/NewRequestPage.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { NotificationsPage } from './pages/NotificationsPage.tsx'
import { OrganizationHomePage } from './pages/OrganizationHomePage.tsx'
import { PeoplePage } from './pages/PeoplePage.tsx'
import { PropertiesPage } from './pages/PropertiesPage.tsx'
import { PropertyPage } from './pages/PropertyPage.tsx'
import { RequestPage } from './pages/RequestPage.tsx'
import { RequestsPage } from './pages/RequestsPage.tsx'
import { ResetPasswordPage } from './pages/ResetPasswordPage.tsx'
import { ResidentsPage } from './pages/ResidentsPage.tsx'
import { SignInPage } from './pages/SignInPage.tsx'
import { WorkOrderPage } from './pages/WorkOrderPage.tsx'
import { ReportsPage } from './pages/ReportsPage.tsx'
import { WorkOrdersPage } from './pages/WorkOrdersPage.tsx'

// The router itself is supplied by main.tsx, so tests can start at any address.
function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/password-reset" element={<ResetPasswordPage />} />
        <Route path="/invitations/accept" element={<AcceptInvitationPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<HomeRedirect />} />
            <Route path="organizations/:organizationId" element={<OrganizationHomePage />} />
            <Route path="organizations/:organizationId/people" element={<PeoplePage />} />
            <Route path="organizations/:organizationId/properties" element={<PropertiesPage />} />
            <Route
              path="organizations/:organizationId/properties/:propertyId"
              element={<PropertyPage />}
            />
            <Route path="organizations/:organizationId/residents" element={<ResidentsPage />} />
            <Route path="organizations/:organizationId/my-home" element={<MyHomePage />} />
            <Route path="organizations/:organizationId/requests" element={<RequestsPage />} />
            <Route
              path="organizations/:organizationId/requests/:requestId"
              element={<RequestPage />}
            />
            <Route path="organizations/:organizationId/help" element={<HelpPage />} />
            <Route path="organizations/:organizationId/reports" element={<ReportsPage />} />
            <Route path="organizations/:organizationId/work-orders" element={<WorkOrdersPage />} />
            <Route
              path="organizations/:organizationId/work-orders/:workOrderId"
              element={<WorkOrderPage />}
            />
            <Route path="organizations/:organizationId/my-jobs" element={<MyJobsPage />} />
            <Route
              path="organizations/:organizationId/my-jobs/:workOrderId"
              element={<JobPage />}
            />
            <Route path="organizations/:organizationId/my-approvals" element={<ApprovalsPage />} />
            <Route
              path="organizations/:organizationId/my-approvals/:estimateId"
              element={<ApprovalPage />}
            />
            <Route
              path="organizations/:organizationId/notifications"
              element={<NotificationsPage />}
            />
            <Route path="organizations/:organizationId/my-requests" element={<MyRequestsPage />} />
            <Route
              path="organizations/:organizationId/my-requests/new"
              element={<NewRequestPage />}
            />
            <Route
              path="organizations/:organizationId/my-requests/:requestId"
              element={<MyRequestPage />}
            />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
