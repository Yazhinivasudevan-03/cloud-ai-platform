import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authApi } from "@/services/authApi";
import { registerAuthFailureHandler, tokenStorage } from "@/services/httpClient";
import type { RegisterPayload, RegisterResponse, RoleName, User } from "@/types";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (identifier: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<RegisterResponse>;
  logout: () => void;
  hasRole: (...roles: RoleName[]) => boolean;
  refreshCurrentUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadCurrentUser = useCallback(async () => {
    if (!tokenStorage.getAccessToken()) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const currentUser = await authApi.me();
      setUser(currentUser);
    } catch {
      tokenStorage.clear();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCurrentUser();
    registerAuthFailureHandler(() => setUser(null));
  }, [loadCurrentUser]);

  const login = useCallback(async (identifier: string, password: string, rememberMe = false) => {
    const tokens = await authApi.login(identifier, password, rememberMe);
    tokenStorage.setTokens(tokens);
    const currentUser = await authApi.me();
    setUser(currentUser);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    // Deliberately does NOT log in afterwards - a fresh account is
    // unverified, and login now correctly 403s with EMAIL_NOT_VERIFIED
    // until the user completes the email verification step. The caller
    // (RegisterPage) uses the returned verification_token/verification_link
    // to show a "check your email" screen instead.
    return authApi.register(payload);
  }, []);

  const logout = useCallback(() => {
    tokenStorage.clear();
    setUser(null);
  }, []);

  const hasRole = useCallback(
    (...roles: RoleName[]) => {
      if (!user) return false;
      if (user.is_superuser) return true;
      return user.roles.some((role) => roles.includes(role.name as RoleName));
    },
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      isAuthenticated: user !== null,
      login,
      register,
      logout,
      hasRole,
      refreshCurrentUser: loadCurrentUser,
    }),
    [user, isLoading, login, register, logout, hasRole, loadCurrentUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
