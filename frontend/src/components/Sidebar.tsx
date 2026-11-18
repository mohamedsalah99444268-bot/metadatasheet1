import { useState, useEffect, useMemo } from "react";
import type { TextBlock, ParsedField, ExtractedTable, Highlight } from "../types";
import { getTextBlocks, getParsedFields, getTables } from "../api";

interface Props {
  documentId: number;
  onHighlight: (h: Highlight | null) => void;
  onNavigate: (page: number) => void;
}

type Tab = "summary" | "tables" | "blocks";

// Document-level fields (not part of a variant)
const DOC_FIELDS: { label: string; type: string }[] = [
  { label: "fabricant", type: "manufacturer" },
  { label: "titre", type: "title" },
  { label: "commande", type: "ordering_section" },
  { label: "RoHS", type: "rohs" },
  { label: "sans plomb", type: "lead_free" },
];

// Fields that describe a part variant
const VARIANT_FIELD_TYPES = new Set(["part_number", "package_name", "package_code", "temperature_grade", "description", "pin_count", "status"]);

/** Group fields by variant_group. Fields without a variant_group are "loose". */
function groupVariants(fields: ParsedField[]) {
  const variants = new Map<string, ParsedField[]>();
  const loose: ParsedField[] = [];

  for (const f of fields) {
    if (f.variant_group && VARIANT_FIELD_TYPES.has(f.field_type)) {
      const group = variants.get(f.variant_group) || [];
      group.push(f);
      variants.set(f.variant_group, group);
    } else if (VARIANT_FIELD_TYPES.has(f.field_type)) {
      loose.push(f);
    }
  }

  return { variants, loose };
}

interface VariantSummary {
  groupId: string;
  entries: ParsedField[];
  fieldsByType: Record<string, ParsedField>;
  partNumber: ParsedField | null;
  avgConfidence: number;
}

function summarizeVariant(groupId: string, groupFields: ParsedField[]): VariantSummary {
  const fieldsByType: Record<string, ParsedField> = {};
  for (const field of groupFields) {
    const current = fieldsByType[field.field_type];
    if (!current || field.confidence > current.confidence) {
      fieldsByType[field.field_type] = field;
    }
  }

  return {
    groupId,
    entries: groupFields,
    fieldsByType,
    partNumber: fieldsByType.part_number ?? null,
    avgConfidence: groupFields.reduce((sum, field) => sum + field.confidence, 0) / groupFields.length,
  };
}

function sortVariants(variants: VariantSummary[]) {
  return [...variants].sort((a, b) => {
    const aPart = a.partNumber?.value ?? "";
    const bPart = b.partNumber?.value ?? "";
    return aPart.localeCompare(bPart);
  });
}

function variantGridStyle(columnCount: number) {
  return {
    gridTemplateColumns: `minmax(180px, 1.9fr) repeat(${columnCount}, minmax(0, 1fr)) 56px`,
  };
}

export default function Sidebar({ documentId, onHighlight, onNavigate }: Props) {
  const [tab, setTab] = useState<Tab>("summary");
  const [blocks, setBlocks] = useState<TextBlock[]>([]);
  const [fields, setFields] = useState<ParsedField[]>([]);
  const [tables, setTables] = useState<ExtractedTable[]>([]);
  const [blockPage, setBlockPage] = useState<number | null>(null);
  const [selectedTableId, setSelectedTableId] = useState<number | null>(null);
  const [hoveredCell, setHoveredCell] = useState<string | null>(null);

  useEffect(() => {
    getTextBlocks(documentId).then(setBlocks).catch(() => {});
    getParsedFields(documentId).then(setFields).catch(() => setFields([]));
    getTables(documentId).then(setTables).catch(() => setTables([]));
  }, [documentId]);

  const pageNumbers = [...new Set(blocks.map((b) => b.page_number))].sort((a, b) => a - b);
  const filteredBlocks = blockPage != null ? blocks.filter((b) => b.page_number === blockPage) : blocks;

  function handleFieldClick(f: ParsedField) {
    onNavigate(f.page_number);
    if (f.x0 != null && f.y0 != null && f.x1 != null && f.y1 != null) {
      onHighlight({ page: f.page_number, x0: f.x0, y0: f.y0, x1: f.x1, y1: f.y1 });
    }
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h2>Données extraites</h2>
      </div>
      <div className="sidebar-tabs">
        <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>Résumé</button>
        <button className={tab === "tables" ? "active" : ""} onClick={() => setTab("tables")}>Tableaux ({tables.length})</button>
        <button className={tab === "blocks" ? "active" : ""} onClick={() => setTab("blocks")}>Blocs ({blocks.length})</button>
      </div>
      <div className="sidebar-content">
        {tab === "summary" && (
          <SummaryView
            fields={fields}
            onFieldClick={handleFieldClick}
          />
        )}
        {tab === "tables" && (
          tables.length === 0 ? <div className="loading">Aucun tableau détecté.</div> : (
            tables.map((t) => (
              <TableView
                key={t.id}
                table={t}
                isSelected={selectedTableId === t.id}
                hoveredCell={hoveredCell}
                onTableClick={() => {
                  setSelectedTableId(t.id);
                  onNavigate(t.page_number);
                  onHighlight({ page: t.page_number, x0: t.x0, y0: t.y0, x1: t.x1, y1: t.y1 });
                }}
                onCellHover={(row, col) => {
                  setHoveredCell(`${t.id}-${row}-${col}`);
                  const cell = t.cells.find((c) => c.row === row && c.col === col);
                  if (cell) onHighlight({ page: t.page_number, x0: cell.x0, y0: cell.y0, x1: cell.x1, y1: cell.y1 });
                }}
                onCellLeave={() => setHoveredCell(null)}
                onCellClick={(row, col) => {
                  const cell = t.cells.find((c) => c.row === row && c.col === col);
                  if (cell) {
                    onNavigate(t.page_number);
                    onHighlight({ page: t.page_number, x0: cell.x0, y0: cell.y0, x1: cell.x1, y1: cell.y1 });
                  }
                }}
              />
            ))
          )
        )}
        {tab === "blocks" && (
          <>
            <div style={{ padding: "4px 8px", display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
              <PageFilterButton page={null} current={blockPage} onClick={setBlockPage} />
              {pageNumbers.map((p) => <PageFilterButton key={p} page={p} current={blockPage} onClick={setBlockPage} />)}
            </div>
            {filteredBlocks.map((b) => (
              <div key={b.id} className="text-block-item" onClick={() => { onNavigate(b.page_number); onHighlight({ page: b.page_number, x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1 }); }}>
                <div className="block-text">{b.text}</div>
                <div className="block-meta">p.{b.page_number} | ({b.x0}, {b.y0}) - ({b.x1}, {b.y1})</div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function PageFilterButton({ page, current, onClick }: { page: number | null; current: number | null; onClick: (p: number | null) => void }) {
  const active = page === current;
  return (
    <button
      onClick={() => onClick(page)}
      className={`page-filter-btn ${active ? "active" : ""}`}
    >
      {page == null ? "Toutes" : `p.${page}`}
    </button>
  );
}


/* ---- Summary: doc-level facts + part variant cards ---- */

type EssentialFieldKey = "manufacturer" | "mfgPartNumber" | "package" | "temp" | "title" | "rohs";

interface EssentialSelection {
  manufacturer: string;
  mfgPartNumber: string;
  package: string;
  temp: string;
  title: string;
  rohs: string;
}

interface PartChoice {
  groupId: string;
  manufacturer: string;
  mfgPartNumber: string;
  package: string;
  temp: string;
  title: string;
  rohs: string;
  confidence: number;
  evidenceField: ParsedField | null;
}

interface SummaryViewProps {
  fields: ParsedField[];
  onFieldClick: (f: ParsedField) => void;
}

const ESSENTIAL_FIELD_META: { key: EssentialFieldKey; label: string }[] = [
  { key: "manufacturer", label: "Fabricant" },
  { key: "mfgPartNumber", label: "Référence fabricant" },
  { key: "package", label: "Boîtier" },
  { key: "temp", label: "Temp." },
  { key: "title", label: "Titre / Description" },
  { key: "rohs", label: "RoHS" },
];

function SummaryView({ fields, onFieldClick }: SummaryViewProps) {
  const { variants } = useMemo(() => groupVariants(fields), [fields]);
  const docFields = useMemo(() => {
    const byType: Record<string, ParsedField> = {};
    for (const f of fields) {
      if (DOC_FIELDS.some((d) => d.type === f.field_type)) {
        if (!byType[f.field_type] || f.confidence > byType[f.field_type].confidence) {
          byType[f.field_type] = f;
        }
      }
    }
    return byType;
  }, [fields]);

  const partChoices = useMemo(() => {
    const manufacturer = docFields.manufacturer?.value ?? "";
    const title = docFields.title?.value ?? "";
    const rohs = docFields.rohs?.value ?? "";

    return sortVariants([...variants.entries()].map(([groupId, groupFields]) => summarizeVariant(groupId, groupFields)))
      .map<PartChoice>((variant) => ({
        groupId: variant.groupId,
        manufacturer,
        mfgPartNumber: variant.partNumber?.value ?? "",
        package: variant.fieldsByType.package_name?.value ?? "",
        temp: variant.fieldsByType.temperature_grade?.value ?? "",
        title,
        rohs,
        confidence: variant.avgConfidence,
        evidenceField: variant.partNumber,
      }))
      .filter((choice) => Boolean(choice.mfgPartNumber));
  }, [docFields, variants]);

  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [packageFilter, setPackageFilter] = useState("all");
  const [tempFilter, setTempFilter] = useState("all");
  const [rohsOnly, setRohsOnly] = useState(false);
  const [topConfidenceOnly, setTopConfidenceOnly] = useState(false);
  const [manualSelection, setManualSelection] = useState<EssentialSelection>({
    manufacturer: "",
    mfgPartNumber: "",
    package: "",
    temp: "",
    title: "",
    rohs: "",
  });

  const selectedChoice = useMemo(
    () => partChoices.find((choice) => choice.groupId === selectedGroupId) ?? partChoices[0] ?? null,
    [partChoices, selectedGroupId]
  );

  const computedSelection = useMemo<EssentialSelection>(() => ({
    manufacturer: selectedChoice?.manufacturer ?? docFields.manufacturer?.value ?? "",
    mfgPartNumber: selectedChoice?.mfgPartNumber ?? "",
    package: selectedChoice?.package ?? "",
    temp: selectedChoice?.temp ?? "",
    title: selectedChoice?.title ?? docFields.title?.value ?? "",
    rohs: selectedChoice?.rohs ?? docFields.rohs?.value ?? "",
  }), [docFields, selectedChoice]);

  useEffect(() => {
    if (!selectedGroupId && partChoices[0]) {
      setSelectedGroupId(partChoices[0].groupId);
    }
  }, [partChoices, selectedGroupId]);

  useEffect(() => {
    setManualSelection(computedSelection);
  }, [computedSelection]);

  const packageOptions = useMemo(
    () => [...new Set(partChoices.map((choice) => choice.package).filter(Boolean))].sort(),
    [partChoices]
  );
  const tempOptions = useMemo(
    () => [...new Set(partChoices.map((choice) => choice.temp).filter(Boolean))].sort(),
    [partChoices]
  );

  const filteredChoices = useMemo(() => {
    let choices = partChoices.filter((choice) => {
      if (search && !choice.mfgPartNumber.toLowerCase().includes(search.toLowerCase())) return false;
      if (packageFilter !== "all" && choice.package !== packageFilter) return false;
      if (tempFilter !== "all" && choice.temp !== tempFilter) return false;
      if (rohsOnly && choice.rohs && !choice.rohs.toLowerCase().includes("rohs")) return false;
      return true;
    });

    if (topConfidenceOnly && choices.length > 0) {
      const threshold = Math.max(...choices.map((choice) => choice.confidence)) - 0.08;
      choices = choices.filter((choice) => choice.confidence >= threshold);
    }

    return choices;
  }, [packageFilter, partChoices, rohsOnly, search, tempFilter, topConfidenceOnly]);

  if (fields.length === 0) {
    return <div className="loading">Aucun champ extrait.</div>;
  }

  return (
    <div className="summary-panel">
      <div className="field-group">
        <div className="field-group-title">Fiche de sélection</div>
        <div className="selection-card">
          <div className="selection-card-header">
            <div>
              <div className="selection-card-title">Sélection finale modifiable</div>
              <div className="selection-card-subtitle">Utilisez les valeurs extraites comme point de départ, puis modifiez librement.</div>
            </div>
            <button className="selection-reset-btn" onClick={() => setManualSelection(computedSelection)}>Réinitialiser</button>
          </div>
          <div className="selection-grid">
            {ESSENTIAL_FIELD_META.map(({ key, label }) => (
              <label key={key} className="selection-field">
                <span>{label}</span>
                <input
                  value={manualSelection[key]}
                  onChange={(event) => setManualSelection((current) => ({ ...current, [key]: event.target.value }))}
                />
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="field-group">
        <div className="field-group-title">Sélectionner une référence</div>
        <div className="variant-selection-hint">Filtrez pour obtenir une courte liste, puis cliquez sur une référence fabricant pour inspecter ses preuves.</div>
        <div className="variant-filter-bar">
          <input
            className="variant-search"
            placeholder="Rechercher une référence"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select value={packageFilter} onChange={(event) => setPackageFilter(event.target.value)}>
            <option value="all">Tous les boîtiers</option>
            {packageOptions.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
          <select value={tempFilter} onChange={(event) => setTempFilter(event.target.value)}>
            <option value="all">Toutes les températures</option>
            {tempOptions.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
          <label className="variant-toggle">
            <input type="checkbox" checked={rohsOnly} onChange={(event) => setRohsOnly(event.target.checked)} />
            <span>RoHS uniquement</span>
          </label>
          <label className="variant-toggle">
            <input type="checkbox" checked={topConfidenceOnly} onChange={(event) => setTopConfidenceOnly(event.target.checked)} />
            <span>Confiance maximale</span>
          </label>
        </div>

        <div className="variant-grid-header" style={variantGridStyle(3)}>
          <span className="variant-grid-col variant-grid-col-part">référence fabricant</span>
          <span className="variant-grid-col">boîtier</span>
          <span className="variant-grid-col">temp.</span>
          <span className="variant-grid-col">RoHS</span>
          <span className="variant-grid-col variant-grid-col-score">score</span>
        </div>

        {filteredChoices.map((choice) => (
          <div
            key={choice.groupId}
            className={`variant-grid-row ${choice.groupId === selectedChoice?.groupId ? "selected" : ""}`}
            style={variantGridStyle(3)}
            onClick={() => {
              setSelectedGroupId(choice.groupId);
              if (choice.evidenceField) {
                onFieldClick(choice.evidenceField);
              }
            }}
            title={choice.mfgPartNumber}
          >
            <span className="variant-grid-col variant-grid-col-part">{choice.mfgPartNumber}</span>
            <span className="variant-grid-col">{choice.package || "—"}</span>
            <span className="variant-grid-col">{choice.temp || "—"}</span>
            <span className="variant-grid-col">{choice.rohs || "—"}</span>
            <span className="variant-grid-col variant-grid-col-score">{Math.round(choice.confidence * 100)}%</span>
          </div>
        ))}

        {filteredChoices.length === 0 && <div className="loading">Aucune référence ne correspond aux filtres actuels.</div>}
      </div>
    </div>
  );
}

/* ---- Table rendering ---- */

interface TableViewProps {
  table: ExtractedTable;
  isSelected: boolean;
  hoveredCell: string | null;
  onTableClick: () => void;
  onCellHover: (row: number, col: number) => void;
  onCellLeave: () => void;
  onCellClick: (row: number, col: number) => void;
}

function TableView({ table, isSelected, hoveredCell, onTableClick, onCellHover, onCellLeave, onCellClick }: TableViewProps) {
  const grid = useMemo(() => {
    const rows: (string | undefined)[][] = [];
    for (let r = 0; r < table.row_count; r++) {
      const row: (string | undefined)[] = [];
      for (let c = 0; c < table.col_count; c++) {
        const cell = table.cells.find((cl) => cl.row === r && cl.col === c);
        row.push(cell?.text);
      }
      rows.push(row);
    }
    return rows;
  }, [table]);

  return (
    <div className={`table-block ${isSelected ? "selected" : ""}`}>
      <div onClick={onTableClick} className="table-block-head">
        <span style={{ fontWeight: 500 }}>Tableau {table.table_index + 1}</span>
        <span>p.{table.page_number} &middot; {table.row_count}&times;{table.col_count}</span>
      </div>
      <div className="table-block-body">
        <table className="data-table compact">
          <tbody>
            {grid.map((row, rIdx) => (
              <tr key={rIdx}>
                {row.map((cellText, cIdx) => {
                  const cellKey = `${table.id}-${rIdx}-${cIdx}`;
                  const isHeader = rIdx === 0 && table.headers.length > 0;
                  const isHovered = hoveredCell === cellKey;
                  return (
                    <td key={cIdx}
                      className={`table-block-cell ${isHeader ? "header" : ""} ${isHovered ? "hovered" : ""}`}
                      onMouseEnter={() => onCellHover(rIdx, cIdx)}
                      onMouseLeave={onCellLeave}
                      onClick={(e) => { e.stopPropagation(); onCellClick(rIdx, cIdx); }}
                      title={cellText || ""}
                    >{cellText || ""}</td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
