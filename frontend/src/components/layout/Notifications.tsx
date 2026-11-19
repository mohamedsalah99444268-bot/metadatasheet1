import { useEffect, useRef, useState } from "react";
import { parseTs } from "../../lib/format";
import { Link } from "react-router-dom";
import { Bell, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { getStatsOverview, listMonitoredJobs } from "../../api";
import { tEnum } from "../../lib/enums";
import { useI18n } from "../../lib/i18n";
import { relTime } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";
import { IconButton } from "../ui";

const SEEN_KEY = "sd_notif_seen";

function readSeen(): number {
  try { return Number(localStorage.getItem(SEEN_KEY) ?? 0) || 0; } catch { return 0; }
}

export default function Notifications() {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState(readSeen);
  const ref = useRef<HTMLDivElement>(null);
  const overview = useQuery((s) => getStatsOverview(s), [], { pollMs: 20000 });
  const active = useQuery((s) => listMonitoredJobs({ status: "active", page_size: 5 }, s), [], { pollMs: 10000 });

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const events = (overview.data?.recent_activity ?? []).slice(0, 12);
  const unread = events.filter((e) => parseTs(e.at).getTime() > seen && (e.status === "failed" || e.status === "completed")).length;
  const activeJobs = active.data?.items ?? [];

  function toggle() {
    setOpen((o) => !o);
    if (!open) {
      const now = Date.now();
      setSeen(now);
      try { localStorage.setItem(SEEN_KEY, String(now)); } catch { /* ignore */ }
    }
  }

  return (
    <div className="popover-anchor" ref={ref}>
      <IconButton icon={Bell} label={t("notif.title")} onClick={toggle} aria-expanded={open} />
      {unread > 0 && <span className="notif-dot tnum" aria-label={t("notif.unread", { n: unread })}>{unread > 9 ? "9+" : unread}</span>}
      {open && (
        <div className="popover notif-pop" role="dialog" aria-label={t("notif.title")}>
          <div className="popover-head"><strong>{t("notif.title")}</strong><Link to="/monitoring" onClick={() => setOpen(false)} className="link small">{t("notif.all")}</Link></div>
          {activeJobs.length > 0 && (
            <div className="notif-section">
              <div className="notif-label">{t("notif.running", { n: active.data?.total ?? activeJobs.length })}</div>
              {activeJobs.map((job) => (
                <Link key={job.id} to={`/monitoring?job=${encodeURIComponent(job.id)}`} className="notif-item" onClick={() => setOpen(false)}>
                  <Loader2 size={15} className="spin text-blue" aria-hidden />
                  <span className="notif-text"><span className="pn">{job.reference ?? job.id.slice(0, 8)}</span><span className="muted small">{tEnum(t, "agent", job.current_agent)} · {Math.round(job.progress)}%</span></span>
                </Link>
              ))}
            </div>
          )}
          <div className="notif-section">
            <div className="notif-label">{t("notif.recent")}</div>
            {overview.error && <p className="text-red small pad-12">{overview.error}</p>}
            {!overview.error && events.length === 0 && <p className="muted small pad-12">{t("notif.empty")}</p>}
            {events.map((e, i) => {
              const Icon = e.status === "failed" ? XCircle : CheckCircle2;
              const body = (
                <>
                  <Icon size={15} className={e.status === "failed" ? "text-red" : "text-green"} aria-hidden />
                  <span className="notif-text"><span>{e.title}</span><span className="muted small">{relTime(e.at, locale)}</span></span>
                </>
              );
              return e.link
                ? <Link key={i} to={e.link} className="notif-item" onClick={() => setOpen(false)}>{body}</Link>
                : <div key={i} className="notif-item">{body}</div>;
            })}
          </div>
        </div>
      )}
    </div>
  );
}
