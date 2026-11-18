import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import { LoadingState, ToastHost } from "./components/ui";
import { AppProvider, useApp } from "./state/AppContext";
import { AuthProvider, useAuth } from "./state/AuthContext";
import DashboardPage from "./pages/DashboardPage";
import UploadArea from "./components/UploadArea";
import ComponentsPage from "./pages/ComponentsPage";
import ComponentDetailPage from "./pages/ComponentDetailPage";
import WorkspacePage from "./pages/WorkspacePage";
import ValidationPage from "./pages/ValidationPage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";
import BatchProcessingPage from "./pages/BatchProcessingPage";
import ResearchPage from "./pages/ResearchPage";
import AgentMonitoringPage from "./pages/AgentMonitoringPage";
import TechnicalSpecsPage from "./pages/TechnicalSpecsPage";
import ComparisonPage from "./pages/ComparisonPage";
import HistoryPage from "./pages/HistoryPage";
import RagPage from "./pages/RagPage";
import UserManagementPage from "./pages/UserManagementPage";
import LoginPage from "./pages/LoginPage";

function CurrentView() {
  const { view } = useApp();
  switch (view) {
    case "dashboard": return <DashboardPage />;
    case "batch": return <BatchProcessingPage />;
    case "agents": return <AgentMonitoringPage />;
    case "history": return <HistoryPage />;
    case "import": return <UploadArea />;
    case "research": return <ResearchPage />;
    case "components": return <ComponentsPage />;
    case "detail": return <ComponentDetailPage />;
    case "workspace": return <WorkspacePage />;
    case "specs": return <TechnicalSpecsPage />;
    case "comparison": return <ComparisonPage />;
    case "validation": return <ValidationPage />;
    case "reports": return <ReportsPage />;
    case "rag": return <RagPage />;
    case "users": return <UserManagementPage />;
    case "settings": return <SettingsPage />;
  }
}

function Application() {
  const { toasts, dismissToast } = useApp();
  return (
    <AppShell>
      <CurrentView />
      <ToastHost toasts={toasts} onDismiss={dismissToast} />
    </AppShell>
  );
}

function ProtectedLayout() {
  const { status, user, loading } = useAuth();
  if (loading) return <LoadingState label="Chargement de l’application…" />;
  if (status?.enabled && !user) return <Navigate to="/login" replace />;
  return (
    <AppProvider>
      <Outlet />
    </AppProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<Application />} />
          <Route path="/dashboard" element={<Application />} />
          <Route path="/batch" element={<Application />} />
          <Route path="/agents" element={<Application />} />
          <Route path="/history" element={<Application />} />
          <Route path="/import" element={<Application />} />
          <Route path="/research" element={<Application />} />
          <Route path="/components" element={<Application />} />
          <Route path="/components/:componentId" element={<Application />} />
          <Route path="/workspace" element={<Application />} />
          <Route path="/workspace/:documentId" element={<Application />} />
          <Route path="/specs" element={<Application />} />
          <Route path="/comparison" element={<Application />} />
          <Route path="/validation" element={<Application />} />
          <Route path="/reports" element={<Application />} />
          <Route path="/rag" element={<Application />} />
          <Route path="/users" element={<Application />} />
          <Route path="/settings" element={<Application />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
