import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { listComponents, type ComponentSummary } from "../../api";
import { tEnum } from "../../lib/enums";
import { useI18n } from "../../lib/i18n";
import { errorMessage } from "../../lib/useQuery";
import { Modal, ThumbIcon } from "../ui";

export default function GlobalSearch() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<ComponentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 0); }, [open]);

  useEffect(() => {
    if (!open || q.trim().length < 2) { setItems([]); setError(null); return; }
    const controller = new AbortController();
    const id = window.setTimeout(() => {
      setLoading(true);
      listComponents({ q: q.trim(), page_size: 8 }, controller.signal)
        .then((res) => { setItems(res.items); setError(null); setActive(0); })
        .catch((e: unknown) => { if (!controller.signal.aborted) setError(errorMessage(e)); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 200);
    return () => { controller.abort(); window.clearTimeout(id); };
  }, [q, open]);

  function go(item: ComponentSummary) {
    setOpen(false);
    setQ("");
    navigate(`/components/${item.id}`);
  }

  return (
    <>
      <button type="button" className="search-trigger" onClick={() => setOpen(true)} aria-label={t("search.open")}>
        <Search size={15} aria-hidden />
        <span className="search-trigger-text">{t("search.placeholder")}</span>
        <kbd>⌘K</kbd>
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={t("search.title")} width={600}>
        <div className="search-box">
          <Search size={16} aria-hidden />
          <input
            ref={inputRef}
            className="input input-bare"
            value={q}
            placeholder={t("search.placeholder")}
            aria-label={t("search.placeholder")}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
              if (e.key === "Enter" && items[active]) go(items[active]);
            }}
          />
        </div>
        <div className="search-results" role="listbox">
          {q.trim().length < 2 && <p className="muted small pad-12">{t("search.hint")}</p>}
          {error && <p className="text-red small pad-12">{error}</p>}
          {!error && q.trim().length >= 2 && !loading && items.length === 0 && <p className="muted small pad-12">{t("search.none", { q })}</p>}
          {items.map((item, index) => (
            <button key={item.id} type="button" role="option" aria-selected={index === active} className={`search-item ${index === active ? "active" : ""}`} onMouseEnter={() => setActive(index)} onClick={() => go(item)}>
              <ThumbIcon category={item.thumbnail_category ?? item.category} size={32} />
              <span className="search-item-main"><span className="pn">{item.part_number}</span><span className="muted small">{item.manufacturer}{item.category ? ` / ${tEnum(t, "cat", item.category)}` : ""}</span></span>
              <span className="muted small tnum">{t("common.specsShort", { n: item.spec_count })}</span>
            </button>
          ))}
        </div>
      </Modal>
    </>
  );
}
