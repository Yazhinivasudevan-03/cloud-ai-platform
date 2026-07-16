import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import type { RoleName } from "@/types";

/** Blocks access to nested routes unless the current user holds one of the
 * given roles (or is_superuser). Distinct from ProtectedRoute: this assumes
 * the user is already authenticated and is about role, not login state. */
export function RoleGuard({ roles }: { roles: RoleName[] }) {
  const { hasRole } = useAuth();

  if (!hasRole(...roles)) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
