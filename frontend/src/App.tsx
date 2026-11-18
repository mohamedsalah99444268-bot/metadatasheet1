import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import { ConfirmProvider, ToastProvider } from "./components/feedback";
import { Loading } from "./components/ui";
import { I18nProvider } from "./lib/i18n";
import { ThemeProvider } from "./lib/theme";
import { AuthProvider, useAuth } from "./state/AuthContext";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ImportPage = lazy(() => import("./pages/ImportPage"));
const ComponentsPage = lazy(() => import("./pages/ComponentsPage"));
const ComponentProfilePage = lazy(() => import("./pages/ComponentProfilePage"));
const ComparePage = lazy(() => import("./pages/ComparePage"));
const ValidationPage = lazy(() => import("./pages/ValidationPage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));
const DatasetsPage = lazy(() => import("./pages/DatasetsPage"));
const MonitoringPage = lazy(() => import("./pages/MonitoringPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));

function ProtectedLayout() {
  const { status, user, loading } = useAuth();
  if (loading) return <Loading />;
  if (status?.enabled && !user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <I18nProvider>
        <ToastProvider>
          <ConfirmProvider>{children}</ConfirmProvider>
        </ToastProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}

export default function App() {
  return (
    <Providers>
      <AuthProvider>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedLayout />}>
              <Route element={<AppShell />}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/import" element={<ImportPage />} />
                <Route path="/components" element={<ComponentsPage />} />
                <Route path="/components/:componentId" element={<ComponentProfilePage />} />
                <Route path="/compare" element={<ComparePage />} />
                <Route path="/validation" element={<ValidationPage />} />
                <Route path="/assistant" element={<AssistantPage />} />
                <Route path="/datasets" element={<DatasetsPage />} />
                <Route path="/monitoring" element={<MonitoringPage />} />
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/users" element={<UsersPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </Providers>
  );
}
