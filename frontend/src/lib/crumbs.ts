import { useEffect, useSyncExternalStore } from "react";

const labels = new Map<string, string>();
const listeners = new Set<() => void>();
let version = 0;
const emit = () => { version++; listeners.forEach((l) => l()); };

/** Lets a page give its breadcrumb a human label (e.g. a part number instead of an id). */
export function useCrumbLabel(path: string, label: string | null | undefined) {
  useEffect(() => {
    if (!label) return;
    labels.set(path, label); emit();
    return () => { labels.delete(path); emit(); };
  }, [path, label]);
}

export function useCrumbLabels(): Map<string, string> {
  useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => version);
  return labels;
}
