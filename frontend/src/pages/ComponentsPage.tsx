import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowDownUp, GitCompareArrows, LayoutGrid, List, Search, X } from "lucide-react";
import { getComponentFacets, listComponents, type ComponentQuery, type ComponentSummary } from "../api";
import { Badge, Button, Card, EmptyState, ErrorState, Loading, PageHeader, Pagination, Segmented, ThumbIcon } from "../components/ui";
import { useToast } from "../components/feedback";
import { fmtDate } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { canCompare, COMPARE_MAX, toggleSelection } from "../lib/selection";
import { useQuery } from "../lib/useQuery";

const PAGE_SIZE = 24;
type SortKey = NonNullable<ComponentQuery["sort"]>;

function SpecBar({ c }: { c: ComponentSummary }) {
  const total = Math.max(1, c.spec_count);
  return (
    <div className="spec-bar" title={`${c.accepted_count} / ${c.pending_count} / ${c.rejected_count}`}>
      <span className="seg seg-green" style={{ width: `${(c.accepted_count / total) * 100}%` }} />
      <span className="seg seg-slate" style={{ width: `${(c.pending_count / total) * 100}%` }} />
      <span className="seg seg-red" style={{ width: `${(c.rejected_count / total) * 100}%` }} />
    </div>
  );
}

export default function ComponentsPage() {
  const { t, locale } = useI18n();
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<number[]>([]);
  const [qInput, setQInput] = useState(params.get("q") ?? "");

  const query: ComponentQuery = {
    q: params.get("q") ?? undefined,
    manufacturer: params.get("manufacturer") ?? undefined,
    category: params.get("category") ?? undefined,
    status: params.get("status") ?? undefined,
    sort: (params.get("sort") as SortKey) ?? "updated_at",
    order: (params.get("order") as "asc" | "desc") ?? "desc",
    page: Number(params.get("page") ?? 1) || 1,
    page_size: PAGE_SIZE,
  };
  const view = params.get("view") === "table" ? "table" : "grid";
  const list = useQuery((s) => listComponents(query, s), [query]);
  const facets = useQuery((s) => getComponentFacets(s), []);

  function set(key: string, value: string | null, resetPage = true) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (resetPage && key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  function toggle(id: number) {
    const res = toggleSelection(selected, id);
    if (res.limited) toast("info", t("components.limit", { n: COMPARE_MAX }));
    setSelected(res.ids);
  }

  const items = list.data?.items ?? [];
  const hasFilters = Boolean(query.q || query.manufacturer || query.category || query.status);

  return (
    <>
      <PageHeader
        title={t("components.title")}
        description={t("components.desc")}
        actions={<Link to="/import" className="btn btn-primary btn-md">{t("nav.import")}</Link>}
      />
      <Card className="toolbar-card">
        <form className="toolbar" onSubmit={(e) => { e.preventDefault(); set("q", qInput.trim() || null); }}>
          <div className="input-icon grow">
            <Search size={15} aria-hidden />
            <input className="input" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder={t("components.searchPh")} aria-label={t("components.searchPh")} />
          </div>
          <select className="input select" aria-label={t("common.manufacturer")} value={query.manufacturer ?? ""} onChange={(e) => set("manufacturer", e.target.value || null)}>
            <option value="">{t("components.allManufacturers")}</option>
            {facets.data?.manufacturers.map((m) => <option key={m.value} value={m.value}>{m.value} ({m.count})</option>)}
          </select>
          <select className="input select" aria-label={t("common.category")} value={query.category ?? ""} onChange={(e) => set("category", e.target.value || null)}>
            <option value="">{t("components.allCategories")}</option>
            {facets.data?.categories.map((m) => <option key={m.value} value={m.value}>{m.value} ({m.count})</option>)}
          </select>
          <select className="input select" aria-label={t("common.status")} value={query.status ?? ""} onChange={(e) => set("status", e.target.value || null)}>
            <option value="">{t("components.allStatuses")}</option>
            {(["pending", "accepted", "rejected", "edited", "needs_review", "conflict"] as const).map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
          </select>
          <select className="input select" aria-label={t("components.sort")} value={`${query.sort}:${query.order}`} onChange={(e) => { const [s, o] = e.target.value.split(":"); const n = new URLSearchParams(params); n.set("sort", s); n.set("order", o); n.delete("page"); setParams(n, { replace: true }); }}>
            <option value="updated_at:desc">{t("components.sort.recent")}</option>
            <option value="part_number:asc">{t("components.sort.pn")}</option>
            <option value="manufacturer:asc">{t("components.sort.manufacturer")}</option>
            <option value="spec_count:desc">{t("components.sort.specs")}</option>
          </select>
          <Segmented label={t("components.view")} value={view} onChange={(v) => set("view", v === "grid" ? null : v, false)} options={[{ value: "grid", label: "", icon: LayoutGrid }, { value: "table", label: "", icon: List }]} />
          {hasFilters && <Button variant="ghost" size="sm" icon={X} onClick={() => { setQInput(""); setParams(new URLSearchParams(view === "table" ? { view } : {}), { replace: true }); }}>{t("common.reset")}</Button>}
        </form>
      </Card>

      {selected.length > 0 && (
        <div className="selection-bar" role="region" aria-label={t("components.selection")}>
          <span className="tnum"><strong>{selected.length}</strong> / {COMPARE_MAX} {t("components.selected")}</span>
          <span className="muted small">{canCompare(selected) ? "" : t("components.pickMore")}</span>
          <div className="row gap-8">
            <Button variant="ghost" size="sm" onClick={() => setSelected([])}>{t("common.clear")}</Button>
            <Button variant="primary" size="sm" icon={GitCompareArrows} disabled={!canCompare(selected)} onClick={() => navigate(`/compare?ids=${selected.join(",")}`)}>{t("components.compare")}</Button>
          </div>
        </div>
      )}

      {list.error && !list.data ? <ErrorState message={list.error} onRetry={list.reload} /> : !list.data ? <Loading rows={6} /> : items.length === 0 ? (
        <EmptyState
          illustration={hasFilters ? "empty-search" : "empty-components"}
          title={hasFilters ? t("components.noMatch") : t("components.empty")}
          description={hasFilters ? t("components.noMatchHint") : t("components.emptyHint")}
          action={hasFilters ? undefined : <Link to="/import" className="btn btn-primary btn-md">{t("nav.import")}</Link>}
        />
      ) : view === "grid" ? (
        <div className="comp-grid">
          {items.map((c) => {
            const on = selected.includes(c.id);
            return (
              <article key={c.id} className={`comp-card ${on ? "selected" : ""}`}>
                <label className="comp-check" title={t("components.selectToCompare")}>
                  <input type="checkbox" checked={on} onChange={() => toggle(c.id)} aria-label={t("components.selectX", { pn: c.part_number })} />
                </label>
                <Link to={`/components/${c.id}`} className="comp-link">
                  <div className="comp-head">
                    <ThumbIcon category={c.thumbnail_category ?? c.category} size={44} />
                    <div className="comp-id">
                      <span className="pn pn-lg">{c.part_number}</span>
                      <span className="muted small">{c.manufacturer}</span>
                    </div>
                  </div>
                  <div className="comp-meta">
                    {c.category && <Badge>{c.category}</Badge>}
                    {c.package && <Badge tone="neutral">{c.package}</Badge>}
                    {c.pin_count != null && <span className="muted small tnum">{c.pin_count} pins</span>}
                  </div>
                  <SpecBar c={c} />
                  <div className="comp-foot muted small tnum">
                    <span>{t("components.specsCount", { n: c.spec_count, a: c.accepted_count })}</span>
                    <span>{fmtDate(c.updated_at, locale, false)}</span>
                  </div>
                </Link>
              </article>
            );
          })}
        </div>
      ) : (
        <Card flush>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="w-check" aria-label={t("components.selection")} />
                  <th><button type="button" className="th-sort" onClick={() => { const n = new URLSearchParams(params); n.set("sort", "part_number"); n.set("order", query.sort === "part_number" && query.order === "asc" ? "desc" : "asc"); setParams(n, { replace: true }); }}>{t("common.partNumber")}<ArrowDownUp size={12} /></button></th>
                  <th>{t("common.manufacturer")}</th><th>{t("common.category")}</th><th>{t("common.package")}</th>
                  <th className="num">Specs</th><th className="num">{t("status.accepted")}</th><th className="num">{t("status.pending")}</th><th className="num">{t("status.rejected")}</th><th>{t("common.updated")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className={selected.includes(c.id) ? "row-selected" : ""}>
                    <td className="w-check"><input type="checkbox" checked={selected.includes(c.id)} onChange={() => toggle(c.id)} aria-label={t("components.selectX", { pn: c.part_number })} /></td>
                    <td><Link to={`/components/${c.id}`} className="pn link-plain">{c.part_number}</Link></td>
                    <td>{c.manufacturer}</td><td>{c.category ?? "—"}</td><td>{c.package ?? "—"}</td>
                    <td className="num">{c.spec_count}</td><td className="num text-green">{c.accepted_count}</td><td className="num">{c.pending_count}</td><td className="num text-red">{c.rejected_count}</td>
                    <td className="muted tnum">{fmtDate(c.updated_at, locale, false)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {list.data && list.data.total > PAGE_SIZE && <Pagination page={query.page ?? 1} pageSize={PAGE_SIZE} total={list.data.total} onPage={(p) => set("page", String(p), false)} />}
    </>
  );
}
