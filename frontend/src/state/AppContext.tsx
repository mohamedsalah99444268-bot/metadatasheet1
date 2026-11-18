import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type {
  AnalysisJob,
  AppToast,
  AppView,
  ComponentCandidate,
  DocumentMeta,
  ExtractedTable,
  FieldKey,
  FieldRevision,
  Highlight,
  ManualFieldValues,
  PageInfo,
  ParsedField,
  ReviewStatus,
  TextBlock,
} from "../types";
import type { AiHealthResponse, HealthResponse } from "../api";
import {
  bulkUpsertReviews,
  deleteAllReviews,
  deleteReview,
  getAiHealth,
  getHealth,
  getImportJob,
  getPages,
  getParsedFields,
  getTables,
  getTextBlocks,
  listDocuments,
  listImportJobs,
  listReviews,
  upsertReview,
  uploadDocument,
} from "../api";
import { allComponents, buildAnalyses } from "../lib/analysis";
import { parsePath, pathForView } from "../navigation";

export interface Preferences {
  compactTables: boolean;
  showSourceText: boolean;
  pageSize: number;
}

const DEFAULT_PREFERENCES: Preferences = {
  compactTables: false,
  showSourceText: true,
  pageSize: 10,
};

const REVIEW_KEY = "metadatasheet.review.v1";
const PREFERENCES_KEY = "metadatasheet.preferences.v1";
const MANUAL_VALUES_KEY = "metadatasheet.manual-values.v1";
const JOBS_KEY = "metadatasheet.jobs.v1";

function readStorage<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeStorage<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    return;
  }
}

interface AppContextValue {
  view: AppView;
  setView: (view: AppView) => void;
  documents: DocumentMeta[];
  fieldsByDocument: Record<number, ParsedField[]>;
  analyses: ReturnType<typeof buildAnalyses>;
  components: ComponentCandidate[];
  dataLoading: boolean;
  dataError: string | null;
  refreshData: () => Promise<void>;

  selectedDocumentId: number | null;
  selectDocument: (id: number | null) => void;
  openDocument: (id: number | null) => void;
  selectedDocument: DocumentMeta | null;
  selectedFields: ParsedField[];
  selectedComponentId: string | null;
  selectedComponent: ComponentCandidate | null;
  selectComponent: (id: string) => void;

  pages: PageInfo[];
  blocks: TextBlock[];
  tables: ExtractedTable[];
  detailLoading: boolean;
  detailError: string | null;

  highlight: Highlight | null;
  targetPage: number | null;
  focusToken: number;
  selectedFieldId: number | null;
  focusField: (field: ParsedField) => void;
  focusArea: (area: Highlight) => void;
  goToPage: (page: number) => void;
  clearHighlight: () => void;

  revisions: Record<number, FieldRevision>;
  reviseField: (fieldId: number, value: string, status: ReviewStatus) => Promise<void>;
  reviseFields: (items: { fieldId: number; value: string; status: ReviewStatus }[]) => Promise<void>;
  resetField: (fieldId: number) => Promise<void>;
  resetAllRevisions: () => Promise<void>;
  manualValues: ManualFieldValues;
  setManualValue: (documentId: number, fieldKey: FieldKey, value: string) => void;

  jobs: AnalysisJob[];
  recordJob: (job: AnalysisJob) => void;
  refreshJob: (jobId: string) => Promise<AnalysisJob | null>;
  jobsBackend: AnalysisJob[];
  jobsBackendLoading: boolean;
  jobsBackendError: string | null;
  refreshJobs: () => Promise<void>;

  toasts: AppToast[];
  pushToast: (kind: AppToast["kind"], message: string) => void;
  dismissToast: (id: number) => void;

  health: HealthResponse | null;
  healthError: string | null;
  healthLoading: boolean;
  refreshHealth: () => Promise<void>;
  aiHealth: AiHealthResponse | null;
  aiHealthError: string | null;
  aiHealthLoading: boolean;
  refreshAiHealth: () => Promise<void>;

  preferences: Preferences;
  setPreferences: (preferences: Preferences) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;

  uploadFile: (file: File) => Promise<number | null>;
  uploading: boolean;
  uploadError: string | null;
  clearUploadError: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Erreur inattendue";
}

export function AppProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const initialRoute = parsePath(location.pathname);
  const [view, setViewState] = useState<AppView>(initialRoute?.view ?? "dashboard");
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [fieldsByDocument, setFieldsByDocument] = useState<Record<number, ParsedField[]>>({});
  const [dataLoading, setDataLoading] = useState(true);
  const [dataError, setDataError] = useState<string | null>(null);

  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(
    initialRoute?.documentId ?? null,
  );
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(
    initialRoute?.componentId ?? null,
  );
  const selectedDocumentIdRef = useRef<number | null>(initialRoute?.documentId ?? null);
  const selectedComponentIdRef = useRef<string | null>(initialRoute?.componentId ?? null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [blocks, setBlocks] = useState<TextBlock[]>([]);
  const [tables, setTables] = useState<ExtractedTable[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [targetPage, setTargetPage] = useState<number | null>(null);
  const [focusToken, setFocusToken] = useState(0);
  const [selectedFieldId, setSelectedFieldId] = useState<number | null>(null);

  const [revisions, setRevisions] = useState<Record<number, FieldRevision>>(() =>
    readStorage<Record<number, FieldRevision>>(REVIEW_KEY, {}),
  );
  const [manualValues, setManualValues] = useState<ManualFieldValues>(() =>
    readStorage<ManualFieldValues>(MANUAL_VALUES_KEY, {}),
  );
  const [jobs, setJobs] = useState<AnalysisJob[]>(() =>
    readStorage<AnalysisJob[]>(JOBS_KEY, []),
  );
  const [jobsBackend, setJobsBackend] = useState<AnalysisJob[]>([]);
  const [jobsBackendLoading, setJobsBackendLoading] = useState(false);
  const [jobsBackendError, setJobsBackendError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<AppToast[]>([]);
  const toastId = useRef(0);

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [aiHealth, setAiHealth] = useState<AiHealthResponse | null>(null);
  const [aiHealthError, setAiHealthError] = useState<string | null>(null);
  const [aiHealthLoading, setAiHealthLoading] = useState(false);

  const [preferences, setPreferencesState] = useState<Preferences>(() =>
    readStorage<Preferences>(PREFERENCES_KEY, DEFAULT_PREFERENCES),
  );
  const [collapsed, setCollapsed] = useState(false);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const setView = useCallback((next: AppView) => {
    navigate(pathForView(next, {
      documentId: selectedDocumentIdRef.current,
      componentId: selectedComponentIdRef.current,
    }));
  }, [navigate]);

  useEffect(() => {
    const route = parsePath(location.pathname);
    if (!route) {
      navigate("/", { replace: true });
      return;
    }
    setViewState(route.view);
    if (route.documentId !== undefined && route.documentId !== selectedDocumentIdRef.current) {
      selectedDocumentIdRef.current = route.documentId;
      setSelectedDocumentId(route.documentId);
    }
    if (route.componentId && route.componentId !== selectedComponentIdRef.current) {
      selectedComponentIdRef.current = route.componentId;
      setSelectedComponentId(route.componentId);
    }
  }, [location.pathname, navigate]);

  const pushToast = useCallback((kind: AppToast["kind"], message: string) => {
    const id = ++toastId.current;
    setToasts((current) => [...current, { id, kind, message }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 5000);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const refreshData = useCallback(async () => {
    setDataLoading(true);
    setDataError(null);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
      const pairs = await Promise.all(
        docs.map(async (doc) => {
          try {
            return [doc.id, await getParsedFields(doc.id)] as const;
          } catch {
            return [doc.id, [] as ParsedField[]] as const;
          }
        }),
      );
      setFieldsByDocument(Object.fromEntries(pairs));
    } catch (error) {
      setDataError(errorMessage(error));
    } finally {
      setDataLoading(false);
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      setHealth(await getHealth());
    } catch (error) {
      setHealth(null);
      setHealthError(errorMessage(error));
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const refreshAiHealth = useCallback(async () => {
    setAiHealthLoading(true);
    setAiHealthError(null);
    try {
      setAiHealth(await getAiHealth());
    } catch (error) {
      setAiHealth(null);
      setAiHealthError(errorMessage(error));
    } finally {
      setAiHealthLoading(false);
    }
  }, []);

  const refreshJobs = useCallback(async () => {
    setJobsBackendLoading(true);
    setJobsBackendError(null);
    try {
      setJobsBackend(await listImportJobs());
    } catch (error) {
      setJobsBackendError(errorMessage(error));
    } finally {
      setJobsBackendLoading(false);
    }
  }, []);

  const loadReviews = useCallback(async () => {
    try {
      const items = await listReviews();
      setRevisions(Object.fromEntries(items.map((item) => [
        item.field_id,
        { value: item.value, status: item.status, updatedAt: item.updated_at },
      ])));
    } catch (error) {
      pushToast("info", `Validations serveur indisponibles : ${errorMessage(error)}`);
    }
  }, [pushToast]);

  useEffect(() => {
    void refreshData();
    void refreshHealth();
    void refreshAiHealth();
    void refreshJobs();
    void loadReviews();
  }, [refreshData, refreshHealth, refreshAiHealth, refreshJobs, loadReviews]);

  useEffect(() => {
    writeStorage(REVIEW_KEY, revisions);
  }, [revisions]);

  useEffect(() => {
    writeStorage(MANUAL_VALUES_KEY, manualValues);
  }, [manualValues]);

  useEffect(() => {
    writeStorage(JOBS_KEY, jobs);
  }, [jobs]);

  useEffect(() => {
    writeStorage(PREFERENCES_KEY, preferences);
  }, [preferences]);

  useEffect(() => {
    if (selectedDocumentId == null) {
      setPages([]);
      setBlocks([]);
      setTables([]);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    Promise.all([
      getPages(selectedDocumentId),
      getTextBlocks(selectedDocumentId),
      getTables(selectedDocumentId),
    ])
      .then(([pageData, blockData, tableData]) => {
        if (!cancelled) {
          setPages(pageData);
          setBlocks(blockData);
          setTables(tableData);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setDetailError(errorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDocumentId]);

  const analyses = useMemo(
    () => buildAnalyses(documents, fieldsByDocument),
    [documents, fieldsByDocument],
  );
  const components = useMemo(() => allComponents(analyses), [analyses]);
  const selectedAnalysis = useMemo(
    () => analyses.find((analysis) => analysis.document.id === selectedDocumentId) ?? null,
    [analyses, selectedDocumentId],
  );

  const selectedComponent = useMemo(() => {
    if (!selectedAnalysis) return null;
    return selectedAnalysis.components.find((item) => item.id === selectedComponentId)
      ?? selectedAnalysis.components[0]
      ?? null;
  }, [selectedAnalysis, selectedComponentId]);

  const selectDocument = useCallback((id: number | null) => {
    selectedDocumentIdRef.current = id;
    selectedComponentIdRef.current = null;
    setSelectedDocumentId(id);
    setSelectedComponentId(null);
    setHighlight(null);
    setTargetPage(null);
    setSelectedFieldId(null);
  }, []);

  const openDocument = useCallback((id: number | null) => {
    selectDocument(id);
    navigate(pathForView("workspace", { documentId: id }));
  }, [navigate, selectDocument]);

  const selectComponent = useCallback((id: string) => {
    selectedComponentIdRef.current = id;
    setSelectedComponentId(id);
  }, []);

  const focusField = useCallback((field: ParsedField) => {
    setSelectedFieldId(field.id);
    setTargetPage(field.page_number);
    setFocusToken((token) => token + 1);
    if (field.x0 != null && field.y0 != null && field.x1 != null && field.y1 != null) {
      setHighlight({ page: field.page_number, x0: field.x0, y0: field.y0, x1: field.x1, y1: field.y1 });
    } else {
      setHighlight(null);
    }
  }, []);

  const focusArea = useCallback((area: Highlight) => {
    setTargetPage(area.page);
    setFocusToken((token) => token + 1);
    setHighlight(area);
  }, []);

  const goToPage = useCallback((page: number) => {
    setTargetPage(page);
    setFocusToken((token) => token + 1);
  }, []);

  const clearHighlight = useCallback(() => {
    setHighlight(null);
    setSelectedFieldId(null);
  }, []);

  const reviseField = useCallback(async (fieldId: number, value: string, status: ReviewStatus) => {
    setRevisions((current) => ({
      ...current,
      [fieldId]: { value, status, updatedAt: new Date().toISOString() },
    }));
    if (status === "unreviewed") return;
    try {
      await upsertReview(fieldId, value, status);
    } catch (error) {
      pushToast("error", `Validation non enregistrée sur le serveur : ${errorMessage(error)}`);
    }
  }, [pushToast]);

  const reviseFields = useCallback(async (
    items: { fieldId: number; value: string; status: ReviewStatus }[],
  ) => {
    if (items.length === 0) return;
    const timestamp = new Date().toISOString();
    setRevisions((current) => {
      const next = { ...current };
      for (const item of items) {
        if (item.status !== "unreviewed") {
          next[item.fieldId] = { value: item.value, status: item.status, updatedAt: timestamp };
        }
      }
      return next;
    });
    try {
      await bulkUpsertReviews(items
        .filter((item): item is { fieldId: number; value: string; status: Exclude<ReviewStatus, "unreviewed"> } => item.status !== "unreviewed")
        .map((item) => ({ field_id: item.fieldId, value: item.value, status: item.status })));
    } catch (error) {
      pushToast("error", `Validations non enregistrées sur le serveur : ${errorMessage(error)}`);
    }
  }, [pushToast]);

  const resetField = useCallback(async (fieldId: number) => {
    setRevisions((current) => {
      const next = { ...current };
      delete next[fieldId];
      return next;
    });
    try {
      await deleteReview(fieldId);
    } catch (error) {
      pushToast("error", `Validation non supprimée sur le serveur : ${errorMessage(error)}`);
    }
  }, [pushToast]);

  const resetAllRevisions = useCallback(async () => {
    setRevisions({});
    try {
      await deleteAllReviews();
    } catch (error) {
      pushToast("error", `Validations non supprimées sur le serveur : ${errorMessage(error)}`);
    }
  }, [pushToast]);

  const setManualValue = useCallback((documentId: number, fieldKey: FieldKey, value: string) => {
    setManualValues((current) => ({
      ...current,
      [documentId]: { ...current[documentId], [fieldKey]: value },
    }));
  }, []);

  const recordJob = useCallback((job: AnalysisJob) => {
    setJobs((current) => [job, ...current.filter((item) => item.job_id !== job.job_id)]);
  }, []);

  const refreshJob = useCallback(async (jobId: string): Promise<AnalysisJob | null> => {
    try {
      const job = await getImportJob(jobId);
      recordJob(job);
      return job;
    } catch {
      return null;
    }
  }, [recordJob]);

  const uploadFile = useCallback(async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadDocument(file);
      await refreshData();
      selectDocument(result.id);
      setView("workspace");
      pushToast("success", `${result.filename} analysé avec succès.`);
      return result.id;
    } catch (error) {
      const message = errorMessage(error);
      setUploadError(message);
      pushToast("error", message);
      return null;
    } finally {
      setUploading(false);
    }
  }, [pushToast, refreshData, selectDocument, setView]);

  const value: AppContextValue = {
    view,
    setView,
    documents,
    fieldsByDocument,
    analyses,
    components,
    dataLoading,
    dataError,
    refreshData,
    selectedDocumentId,
    selectDocument,
    openDocument,
    selectedDocument: selectedAnalysis?.document ?? null,
    selectedFields: selectedAnalysis?.fields ?? [],
    selectedComponentId: selectedComponent?.id ?? null,
    selectedComponent,
    selectComponent,
    pages,
    blocks,
    tables,
    detailLoading,
    detailError,
    highlight,
    targetPage,
    focusToken,
    selectedFieldId,
    focusField,
    focusArea,
    goToPage,
    clearHighlight,
    revisions,
    reviseField,
    reviseFields,
    resetField,
    resetAllRevisions,
    manualValues,
    setManualValue,
    jobs,
    recordJob,
    refreshJob,
    jobsBackend,
    jobsBackendLoading,
    jobsBackendError,
    refreshJobs,
    toasts,
    pushToast,
    dismissToast,
    health,
    healthError,
    healthLoading,
    refreshHealth,
    aiHealth,
    aiHealthError,
    aiHealthLoading,
    refreshAiHealth,
    preferences,
    setPreferences: setPreferencesState,
    collapsed,
    setCollapsed,
    uploadFile,
    uploading,
    uploadError,
    clearUploadError: () => setUploadError(null),
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp doit être utilisé dans AppProvider");
  return context;
}
