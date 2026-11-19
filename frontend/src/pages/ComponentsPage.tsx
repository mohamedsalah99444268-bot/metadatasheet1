import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowDownUp, GitCompareArrows, LayoutGrid, List, Search, X } from "lucide-react";
import { getComponentFacets, listComponents, type ComponentQuery, type ComponentSummary, type Facets } from "../api";
import { Badge, Button, Card, EmptyState, ErrorState, Loading, PageHeader, Pagination, Segmented, ThumbIcon, Checkbox } from "../components/ui";
import { useToast } from "../components/feedback";
import { fmtDate, fmtNumber } from "../lib/format";
import { tEnum } from "../lib/enums";
import { useI18n, type TFn } from "../lib/i18n";
import { canCompare, COMPARE_MAX, toggleSelection } from "../lib/selection";
import { useQuery } from "../lib/useQuery";

const PAGE_SIZE = 24;
type SortKey = NonNullable<ComponentQuery["sort"]>;

function SpecBar({ c, label }: { c: ComponentSummary; label: string }) {
  const pct = c.spec_count ? Math.round((c.accepted_count / c.spec_count) * 100) : 0;
  return (
    <div className="spec-progress">
      <div className="spec-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}><span className="seg seg-blue" style={{ width: `${pct}%` }} /></div>
      <span className="small tnum muted">{label}</span>
    </div>
  );
}

function Summary({ items, facets, t, locale }: { items: ComponentSummary[]; facets: Facets | null; t: TFn; locale: string }) {
  const specs = items.reduce((n, c) => n + c.spec_count, 0);
  const accepted = items.reduce((n, c) => n + c.accepted_count, 0);
  const pending = items.reduce((n, c) => n + c.pending_count, 0);
  return (
    <div className="comp-summary">
      <div className="sum-stats">
        <div><span>{t("components.sumComponents")}</span><strong className="tnum">{fmtNumber(items.length, locale)}</strong></div>
        <div><span>{t("components.sumSpecs")}</span><strong className="tnum">{fmtNumber(specs, locale)}</strong></div>
        <div><span>{t("components.sumAccepted")}</span><strong className="tnum">{fmtNumber(accepted, locale)}</strong></div>
        <div><span>{t("components.sumPending")}</span><strong className="tnum">{fmtNumber(pending, locale)}</strong></div>
      </div>
      {facets && (
        <div className="sum-facets">
          <div><span className="sum-title">{t("components.byCategory")}</span><div className="row gap-8 wrap">{facets.categories.map((f) => <Link key={f.value} className="facet-chip" to={`/components?category=${encodeURIComponent(f.value)}`}>{tEnum(t, "cat", f.value)}<span className="tnum">{f.count}</span></Link>)}</div></div>
          <div><span className="sum-title">{t("components.byManufacturer")}</span><div className="row gap-8 wrap">{facets.manufacturers.map((f) => <Link key={f.value} className="facet-chip" to={`/components?manufacturer=${encodeURIComponent(f.value)}`}>{f.value}<span className="tnum">{f.count}</span></Link>)}</div></div>
        </div>
      )}
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
        <form className="toolbar comp-toolbar" onSubmit={(e) => { e.preventDefault(); set("q", qInput.trim() || null); }}>
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
            {facets.data?.categories.map((m) => <option key={m.value} value={m.value}>{tEnum(t, "cat", m.value)} ({m.count})</option>)}
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
          <div className="toolbar-end"><Segmented label={t("components.view")} value={view} onChange={(v) => set("view", v === "grid" ? null : v, false)} options={[{ value: "grid", label: "", icon: LayoutGrid }, { value: "table", label: "", icon: List }]} /></div>
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

      {items.length > 0 && <Summary items={items} facets={facets.data ?? null} t={t} locale={locale} />}
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
                  <Checkbox checked={on} onChange={() => toggle(c.id)} aria-label={t("components.selectX", { pn: c.part_number })} />
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
                    {c.category && <Badge>{tEnum(t, "cat", c.category)}</Badge>}
                    {c.package && <Badge tone="neutral">{c.package}</Badge>}
                    {c.pin_count != null && <span className="muted small tnum">{t("common.pins", { n: c.pin_count })}</span>}
                  </div>
                  <SpecBar c={c} label={t("components.validated", { p: c.spec_count ? Math.round((c.accepted_count / c.spec_count) * 100) : 0 })} />
                  <div className="comp-foot muted small tnum">
                    <span>{t("components.specsCount", { n: c.spec_count, a: c.accepted_count })}</span>
                    <span>{fmtDate(c.updated_at, locale, false)}</span>
                  </div>
                </Link>
              </article>
            );
          })}
        </div>
      ) : null}
      {view === "grid" && items.length > 0 && items.length <= 4 && (
        <Card title={t("components.progressTitle")} subtitle={t("components.progressSub")} className="progress-card" flush>
          <ul className="progress-list">
            {items.map((c) => {
              const pend = Math.max(0, c.spec_count - c.accepted_count);
              return (
                <li key={c.id}>
                  <Link to={`/components/${c.id}`} className="pn">{c.part_number}</Link>
                  <span className="stack-bar" role="img" aria-label={`${c.accepted_count} / ${c.spec_count}`}><span style={{ flex: c.accepted_count, background: "var(--green)" }} /><span style={{ flex: pend, background: "var(--border-strong)" }} /></span>
                  <span className="muted small tnum">{t("components.progressRow", { a: c.accepted_count, n: c.spec_count })}</span>
                  <Link to={`/validation?q=${encodeURIComponent(c.part_number)}`} className="btn btn-secondary btn-sm">{t("components.reviewCta", { n: pend })}</Link>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
      {list.data && items.length > 0 && view !== "grid" && (
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
                    <td className="w-check"><Checkbox checked={selected.includes(c.id)} onChange={() => toggle(c.id)} aria-label={t("components.selectX", { pn: c.part_number })} /></td>
                    <td><Link to={`/components/${c.id}`} className="pn link-plain">{c.part_number}</Link></td>
                    <td>{c.manufacturer}</td><td>{tEnum(t, "cat", c.category)}</td><td>{c.package ?? "—"}</td>
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
