import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  getAccessToken,
  getAuthStatus,
  getMe,
  login as loginRequest,
  logoutAuth,
  setAccessToken,
  setUnauthorizedRedirect,
  clearAccessToken,
  type AuthStatus,
  type AuthUser,
  type LoginPayload,
} from "../api";

interface AuthContextValue {
  status: AuthStatus | null;
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Erreur inattendue";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUnauthorizedRedirect(() => {
      if (window.location.pathname !== "/login") navigate("/login");
    });
    return () => setUnauthorizedRedirect(null);
  }, [navigate]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextStatus = await getAuthStatus();
      setStatus(nextStatus);
      if (nextStatus.enabled && getAccessToken()) {
        try {
          setUser(await getMe());
        } catch {
          setUser(null);
        }
      } else {
        setUser(null);
      }
    } catch (reason) {
      setStatus(null);
      setUser(null);
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (payload: LoginPayload) => {
    const result = await loginRequest(payload);
    setAccessToken(result.access_token);
    setUser(result.user);
    setStatus((current) => current ?? { enabled: true, bootstrapped: true });
    setError(null);
    navigate("/");
  }, [navigate]);

  const logout = useCallback(async () => {
    try {
      await logoutAuth();
    } catch {
      return;
    } finally {
      clearAccessToken();
      setUser(null);
      navigate("/login");
    }
  }, [navigate]);

  return (
    <AuthContext.Provider value={{ status, user, loading, error, refresh, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans AuthProvider");
  return context;
}
