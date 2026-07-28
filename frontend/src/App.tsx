import { Route, Routes } from "react-router-dom";
import { AuthLayout } from "@/layouts/AuthLayout";
import { AppLayout } from "@/layouts/AppLayout";
import { PublicLayout } from "@/layouts/PublicLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { RoleGuard } from "@/components/RoleGuard";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { VerifyEmailPage } from "@/pages/VerifyEmailPage";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
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
      <Route element={<PublicLayout />}>
        <Route path="/" element={<LandingPage />} />
      </Route>

      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/microservices/:microserviceId" element={<MicroserviceDetailPage />} />
          <Route path="/deployments/:deploymentId" element={<DeploymentDetailPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/optimization" element={<OptimizationPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/cloud-accounts" element={<CloudAccountsPage />} />
          <Route path="/cloud-accounts/:accountId" element={<CloudAccountDetailPage />} />
          <Route path="/profile" element={<SettingsPage />} />
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
