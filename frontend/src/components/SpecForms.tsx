import { useEffect, useState, type FormEvent } from "react";
import { paramLabel } from "../lib/paramLabels";
import { Check, FileText, MoreHorizontal, Pencil, X } from "lucide-react";
import { acceptSpec, addSpec, editSpec, rejectSpec, type Spec, type SpecCreate, type SpecEdit } from "../api";
import { useI18n } from "../lib/i18n";
import { errorMessage } from "../lib/useQuery";
import { useToast } from "./feedback";
import { Button, Field, Modal } from "./ui";

const CATEGORIES = ["electrical", "thermal", "mechanical", "timing", "interface", "memory", "identity", "other"] as const;
const CONDITIONS = ["absolute_maximum", "recommended_operating", "electrical_characteristics", "general"] as const;

function num(value: string): number | null {
  if (value.trim() === "") return null;
  const n = Number(value.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}
const str = (v: number | null | undefined) => (v == null ? "" : String(v));

/** Review actions bound to the real /specs endpoints; returns updated Spec or null on failure. */
export function useSpecActions(onChange: (spec: Spec) => void) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState<number | null>(null);
  async function run(id: number, fn: () => Promise<Spec>, okKey: "validation.accepted" | "validation.rejected" | "validation.saved") {
    setBusy(id);
    try {
      const updated = await fn();
      onChange(updated);
      toast("success", t(okKey));
      return updated;
    } catch (e) {
      toast("error", errorMessage(e));
      return null;
    } finally {
      setBusy(null);
    }
  }
  return {
    busy,
    accept: (s: Spec, comment?: string) => run(s.id, () => acceptSpec(s.id, comment), "validation.accepted"),
    reject: (s: Spec, comment?: string) => run(s.id, () => rejectSpec(s.id, comment), "validation.rejected"),
    edit: (s: Spec, body: SpecEdit) => run(s.id, () => editSpec(s.id, body), "validation.saved"),
  };
}

export function EditSpecModal({ spec, onClose, onSave }: { spec: Spec | null; onClose: () => void; onSave: (s: Spec, body: SpecEdit) => Promise<unknown> }) {
  const { t, lang } = useI18n();
  const [form, setForm] = useState({ value_text: "", unit: "", min: "", typ: "", max: "", test_condition: "", page: "", comment: "" });
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (spec) setForm({ value_text: spec.value_text ?? "", unit: spec.unit ?? "", min: str(spec.min_value), typ: str(spec.typ_value), max: str(spec.max_value), test_condition: spec.test_condition ?? "", page: str(spec.page_number), comment: "" });
  }, [spec]);
  if (!spec) return null;
  const up = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!spec) return;
    setSaving(true);
    const res = await onSave(spec, {
      value_text: form.value_text, unit: form.unit, min_value: num(form.min), typ_value: num(form.typ), max_value: num(form.max),
      test_condition: form.test_condition, page_number: num(form.page), comment: form.comment || undefined,
    });
    setSaving(false);
    if (res) onClose();
  }
  return (
    <Modal open onClose={onClose} title={t("validation.editTitle", { p: paramLabel(spec.parameter, spec.label, lang) })} width={600}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button variant="primary" type="submit" form="spec-edit" loading={saving}>{t("common.save")}</Button></>}>
      <form id="spec-edit" className="form-stack" onSubmit={(e) => void submit(e)}>
        <div className="form-row"><Field label={t("spec.value")}><input className="input mono" value={form.value_text} onChange={up("value_text")} /></Field><Field label={t("spec.unit")} className="w-120"><input className="input mono" value={form.unit} onChange={up("unit")} /></Field></div>
        <div className="form-row three"><Field label="Min"><input className="input mono" inputMode="decimal" value={form.min} onChange={up("min")} /></Field><Field label="Typ"><input className="input mono" inputMode="decimal" value={form.typ} onChange={up("typ")} /></Field><Field label="Max"><input className="input mono" inputMode="decimal" value={form.max} onChange={up("max")} /></Field></div>
        <div className="form-row"><Field label={t("spec.condition")}><input className="input" value={form.test_condition} onChange={up("test_condition")} /></Field><Field label={t("spec.page")} className="w-120"><input className="input tnum" inputMode="numeric" value={form.page} onChange={up("page")} /></Field></div>
        <Field label={t("spec.comment")}><textarea className="input" rows={2} value={form.comment} onChange={up("comment")} /></Field>
        {spec.source_text && <blockquote className="evidence"><span className="muted small">{t("spec.evidence")}</span>{spec.source_text}</blockquote>}
      </form>
    </Modal>
  );
}

export function AddSpecModal({ componentId, open, onClose, onAdded }: { componentId: number | null; open: boolean; onClose: () => void; onAdded: (s: Spec) => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const empty = { parameter: "", label: "", category: "electrical", condition_type: "electrical_characteristics", value_text: "", unit: "", min: "", typ: "", max: "", page: "", source_text: "", comment: "" };
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) setForm(empty); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!open || componentId == null) return null;
  const up = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (componentId == null) return;
    setSaving(true);
    const body: SpecCreate = {
      parameter: form.parameter.trim(), label: form.label.trim() || undefined, category: form.category, condition_type: form.condition_type,
      value_text: form.value_text.trim(), unit: form.unit || undefined, min_value: num(form.min), typ_value: num(form.typ), max_value: num(form.max),
      page_number: num(form.page), source_text: form.source_text || undefined, comment: form.comment || undefined,
    };
    try {
      const spec = await addSpec(componentId, body);
      toast("success", t("validation.added"));
      onAdded(spec);
      onClose();
    } catch (err) {
      toast("error", errorMessage(err));
    } finally {
      setSaving(false);
    }
  }
  return (
    <Modal open onClose={onClose} title={t("validation.addTitle")} width={640}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button variant="primary" type="submit" form="spec-add" loading={saving}>{t("validation.add")}</Button></>}>
      <form id="spec-add" className="form-stack" onSubmit={(e) => void submit(e)}>
        <div className="form-row"><Field label={t("spec.parameter")} hint="supply_voltage"><input className="input mono" required value={form.parameter} onChange={up("parameter")} /></Field><Field label={t("spec.label")}><input className="input" value={form.label} onChange={up("label")} /></Field></div>
        <div className="form-row">
          <Field label={t("common.category")}><select className="input select" value={form.category} onChange={up("category")}>{CATEGORIES.map((c) => <option key={c} value={c}>{t(`cat.${c}`)}</option>)}</select></Field>
          <Field label={t("spec.conditionType")}><select className="input select" value={form.condition_type} onChange={up("condition_type")}>{CONDITIONS.map((c) => <option key={c} value={c}>{t(`cond.${c}`)}</option>)}</select></Field>
        </div>
        <div className="form-row"><Field label={t("spec.value")}><input className="input mono" required value={form.value_text} onChange={up("value_text")} /></Field><Field label={t("spec.unit")} className="w-120"><input className="input mono" value={form.unit} onChange={up("unit")} /></Field></div>
        <div className="form-row three"><Field label="Min"><input className="input mono" inputMode="decimal" value={form.min} onChange={up("min")} /></Field><Field label="Typ"><input className="input mono" inputMode="decimal" value={form.typ} onChange={up("typ")} /></Field><Field label="Max"><input className="input mono" inputMode="decimal" value={form.max} onChange={up("max")} /></Field></div>
        <div className="form-row"><Field label={t("spec.page")} className="w-120"><input className="input tnum" inputMode="numeric" value={form.page} onChange={up("page")} /></Field><Field label={t("spec.evidence")}><input className="input" value={form.source_text} onChange={up("source_text")} /></Field></div>
        <Field label={t("spec.comment")}><textarea className="input" rows={2} value={form.comment} onChange={up("comment")} /></Field>
      </form>
    </Modal>
  );
}

/** Tinted accept / reject / edit row actions, shared by every spec table. */
export function SpecRowActions({ spec, busy, onAccept, onReject, onEdit, hints = false }: {
  spec: Spec; busy: boolean; onAccept: () => void; onReject: () => void; onEdit: () => void; hints?: boolean;
}) {
  const { t, lang } = useI18n();
  const label = paramLabel(spec.parameter, spec.label, lang);
  return (
    <div className="row-actions">
      <button type="button" className="act act-accept" aria-label={t("validation.accept")} title={`${t("validation.accept")} — ${label}${hints ? " (A)" : ""}`} disabled={busy} onClick={onAccept}><Check size={15} aria-hidden /><span className="act-label">{t("validation.accept")}</span></button>
      <button type="button" className="act act-reject" aria-label={t("validation.reject")} title={`${t("validation.reject")} — ${label}${hints ? " (R)" : ""}`} disabled={busy} onClick={onReject}><X size={15} aria-hidden /><span className="act-label">{t("validation.reject")}</span></button>
      <button type="button" className="act act-edit" aria-label={t("validation.edit")} title={`${t("validation.edit")} — ${label}${hints ? " (E)" : ""}`} onClick={onEdit}><Pencil size={14} aria-hidden /><span className="act-label">{t("validation.edit")}</span></button>
    </div>
  );
}

/** Mobile overflow: one "⋯" button opening an action sheet (Accepter / Rejeter / Modifier / Voir la page). */
export function SpecOverflow({ spec, busy, onAccept, onReject, onEdit, onPage }: {
  spec: Spec; busy: boolean; onAccept: () => void; onReject: () => void; onEdit: () => void; onPage?: () => void;
}) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const label = paramLabel(spec.parameter, spec.label, lang);
  const run = (fn: () => void) => () => { setOpen(false); fn(); };
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <>
      <button type="button" className="m-more" aria-label={`${t("common.more")} — ${label}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}><MoreHorizontal size={18} aria-hidden /></button>
      {open && (
        <div className="sheet-backdrop" onClick={() => setOpen(false)}>
          <div className="sheet" role="dialog" aria-modal="true" aria-label={label} onClick={(e) => e.stopPropagation()}>
            <div className="sheet-head"><strong>{label}</strong>{spec.value_text && <span className="muted mono small"> · {spec.value_text.slice(0, 40)}</span>}</div>
            <button type="button" className="act act-accept sheet-item" disabled={busy} onClick={run(onAccept)}><Check size={16} aria-hidden />{t("validation.accept")}</button>
            <button type="button" className="act act-reject sheet-item" disabled={busy} onClick={run(onReject)}><X size={16} aria-hidden />{t("validation.reject")}</button>
            <button type="button" className="act act-edit sheet-item" onClick={run(onEdit)}><Pencil size={16} aria-hidden />{t("validation.edit")}</button>
            {onPage && <button type="button" className="act sheet-item" onClick={run(onPage)}><FileText size={16} aria-hidden />{t("common.openPage")}</button>}
            <button type="button" className="btn btn-secondary btn-md sheet-cancel" onClick={() => setOpen(false)}>{t("common.cancel")}</button>
          </div>
        </div>
      )}
    </>
  );
}
