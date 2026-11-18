import {
  Activity, BarChart3, Bot, Boxes, ClipboardCheck, Cpu, FileDown, GitCompareArrows, LayoutDashboard,
  Settings, Table2, Upload, Users, type LucideIcon,
} from "lucide-react";
import type { DictKey } from "../../lib/dict";

export interface NavItem { path: string; label: DictKey; icon: LucideIcon; admin?: boolean }
export interface NavGroup { label: DictKey; items: NavItem[] }

export const NAV: NavGroup[] = [
  { label: "nav.group.overview", items: [
    { path: "/dashboard", label: "nav.dashboard", icon: LayoutDashboard },
    { path: "/monitoring", label: "nav.monitoring", icon: Activity },
  ] },
  { label: "nav.group.datasheets", items: [
    { path: "/import", label: "nav.import", icon: Upload },
    { path: "/components", label: "nav.components", icon: Boxes },
    { path: "/compare", label: "nav.compare", icon: GitCompareArrows },
    { path: "/validation", label: "nav.validation", icon: ClipboardCheck },
    { path: "/assistant", label: "nav.assistant", icon: Bot },
    { path: "/reports", label: "nav.reports", icon: FileDown },
  ] },
  { label: "nav.group.data", items: [
    { path: "/datasets", label: "nav.datasets", icon: Table2 },
  ] },
  { label: "nav.group.admin", items: [
    { path: "/users", label: "nav.users", icon: Users, admin: true },
    { path: "/settings", label: "nav.settings", icon: Settings },
  ] },
];

export const ROUTE_LABELS: Record<string, DictKey> = Object.fromEntries(
  NAV.flatMap((g) => g.items.map((i) => [i.path.slice(1), i.label])),
);

export const BRAND_ICONS = { Cpu, BarChart3 };
