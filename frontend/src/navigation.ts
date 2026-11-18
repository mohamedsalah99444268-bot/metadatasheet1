import type { AppView } from "./types";

export const VIEW_PATHS: Record<AppView, string> = {
  dashboard: "/",
  batch: "/batch",
  agents: "/agents",
  history: "/history",
  import: "/import",
  research: "/research",
  components: "/components",
  detail: "/components/:componentId",
  workspace: "/workspace",
  specs: "/specs",
  comparison: "/comparison",
  validation: "/validation",
  reports: "/reports",
  rag: "/rag",
  users: "/users",
  settings: "/settings",
};

export interface PathOptions {
  documentId?: number | null;
  componentId?: string | null;
}

export interface ParsedRoute {
  view: AppView;
  documentId?: number | null;
  componentId?: string | null;
}

export function pathForView(view: AppView, options: PathOptions = {}): string {
  if (view === "workspace") {
    return options.documentId != null
      ? `/workspace/${options.documentId}`
      : "/workspace";
  }
  if (view === "detail") {
    return options.componentId
      ? `/components/${encodeURIComponent(options.componentId)}`
      : "/components";
  }
  return VIEW_PATHS[view];
}

export function parsePath(pathname: string): ParsedRoute | null {
  const path = pathname.replace(/\/+$/, "") || "/";
  const componentMatch = path.match(/^\/components\/([^/]+)$/);
  if (componentMatch) {
    const componentId = decodeURIComponent(componentMatch[1]);
    const documentMatch = componentId.match(/^(\d+):/);
    return {
      view: "detail",
      componentId,
      ...(documentMatch ? { documentId: Number(documentMatch[1]) } : {}),
    };
  }
  const workspaceMatch = path.match(/^\/workspace\/(\d+)$/);
  if (workspaceMatch) return { view: "workspace", documentId: Number(workspaceMatch[1]) };
  if (path === "/workspace") return { view: "workspace", documentId: null };

  const entry = (Object.entries(VIEW_PATHS) as [AppView, string][]).find(
    ([view, template]) => view !== "detail" && view !== "workspace" && template === path,
  );
  return entry ? { view: entry[0] } : null;
}
