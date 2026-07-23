import { Route, Routes } from "react-router-dom";
import { AuthLayout } from "@/layouts/AuthLayout";
import { AppLayout } from "@/layouts/AppLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { RoleGuard } from "@/components/RoleGuard";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import { MicroserviceDetailPage } from "@/pages/MicroserviceDetailPage";
import { DeploymentDetailPage } from "@/pages/DeploymentDetailPage";
import { AlertsPage } from "@/pages/AlertsPage";
import { OptimizationPage } from "@/pages/OptimizationPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { CloudAccountsPage } from "@/pages/CloudAccountsPage";
import { CloudAccountDetailPage } from "@/pages/CloudAccountDetailPage";
import { UsersPage } from "@/pages/UsersPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { NotificationSettingsPage } from "@/pages/NotificationSettingsPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/microservices/:microserviceId" element={<MicroserviceDetailPage />} />
          <Route path="/deployments/:deploymentId" element={<DeploymentDetailPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/optimization" element={<OptimizationPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/cloud-accounts" element={<CloudAccountsPage />} />
          <Route path="/cloud-accounts/:accountId" element={<CloudAccountDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/notification-settings" element={<NotificationSettingsPage />} />

          <Route element={<RoleGuard roles={["admin"]} />}>
            <Route path="/users" element={<UsersPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
