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
  { label: "Manufacturer", type: "manufacturer" },
  { label: "Title / Description", type: "title" },
  { label: "Ordering Info", type: "ordering_section" },
  { label: "RoHS", type: "rohs" },
  { label: "Lead-Free", type: "lead_free" },
];

// Fields that describe a part variant
const VARIANT_FIELD_TYPES = new Set(["part_number", "package_name", "package_code", "temperature_grade", "description", "pin_count", "status"]);

// Human-readable labels for variant fields
const VARIANT_LABELS: Record<string, string> = {
  part_number: "Part Number",
  package_name: "Package",
  package_code: "Package Code",
  temperature_grade: "Temperature",
  description: "Description",
  pin_count: "Pins",
  status: "Status",
};

function confidenceBadge(c: number) {
  const cls = c >= 0.8 ? "confidence-high" : c >= 0.5 ? "confidence-medium" : "confidence-low";
  return <span className={`confidence-badge ${cls}`}>{Math.round(c * 100)}%</span>;
}

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

export default function Sidebar({ documentId, onHighlight, onNavigate }: Props) {
  const [tab, setTab] = useState<Tab>("summary");
  const [blocks, setBlocks] = useState<TextBlock[]>([]);
  const [fields, setFields] = useState<ParsedField[]>([]);
  const [tables, setTables] = useState<ExtractedTable[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
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
    setSelectedId(f.id);
    onNavigate(f.page_number);
    if (f.x0 != null && f.y0 != null && f.x1 != null && f.y1 != null) {
      onHighlight({ page: f.page_number, x0: f.x0, y0: f.y0, x1: f.x1, y1: f.y1 });
    }
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h2>Extracted Data</h2>
      </div>
      <div className="sidebar-tabs">
        <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>Summary</button>
        <button className={tab === "tables" ? "active" : ""} onClick={() => setTab("tables")}>Tables ({tables.length})</button>
        <button className={tab === "blocks" ? "active" : ""} onClick={() => setTab("blocks")}>Blocks ({blocks.length})</button>
      </div>
      <div className="sidebar-content">
        {tab === "summary" && (
          <SummaryView
            fields={fields}
            selectedId={selectedId}
            expandedSection={expandedSection}
            onToggleSection={(s) => setExpandedSection(expandedSection === s ? null : s)}
            onFieldClick={handleFieldClick}
          />
        )}
        {tab === "tables" && (
          tables.length === 0 ? <div className="loading">No tables detected.</div> : (
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
      style={{
        fontSize: 11, padding: "2px 8px", border: "1px solid #ddd",
        borderRadius: 4, background: active ? "#2563eb" : "#fff",
        color: active ? "#fff" : "#333", cursor: "pointer",
      }}
    >
      {page == null ? "All" : `p.${page}`}
    </button>
  );
}


/* ---- Summary: doc-level facts + part variant cards ---- */

interface SummaryViewProps {
  fields: ParsedField[];
  selectedId: number | null;
  expandedSection: string | null;
  onToggleSection: (section: string) => void;
  onFieldClick: (f: ParsedField) => void;
}

function SummaryView({ fields, selectedId, expandedSection, onToggleSection, onFieldClick }: SummaryViewProps) {
  const { variants, loose } = useMemo(() => groupVariants(fields), [fields]);
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

  if (fields.length === 0) {
    return <div className="loading">No fields extracted.</div>;
  }

  return (
    <div style={{ padding: "4px 0" }}>
      {/* Document-level facts */}
      <div className="field-group">
        <div className="field-group-title">Document</div>
        {DOC_FIELDS.map(({ label, type }) => {
          const f = docFields[type];
          if (!f) return null;
          return (
            <div key={type} className={`field-row ${selectedId === f.id ? "selected" : ""}`} onClick={() => onFieldClick(f)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ fontSize: 11, color: "#888", marginBottom: 2 }}>{label}</div>
                {confidenceBadge(f.confidence)}
              </div>
              <div className="field-value">{f.value}</div>
              <div className="field-meta"><span>p.{f.page_number}</span></div>
            </div>
          );
        })}
      </div>

      {/* Part variants from tables */}
      {variants.size > 0 && (
        <div className="field-group">
          <div className="field-group-title">Part Variants ({variants.size})</div>
          {[...variants.entries()].map(([groupId, groupFields]) => {
            const pn = groupFields.find((f) => f.field_type === "part_number");
            const pkg = groupFields.find((f) => f.field_type === "package_name");
            const temp = groupFields.find((f) => f.field_type === "temperature_grade");
            const isExpanded = expandedSection === groupId;
            const avgConf = groupFields.reduce((s, f) => s + f.confidence, 0) / groupFields.length;

            return (
              <div key={groupId} style={{ marginBottom: 4 }}>
                {/* Compact variant card */}
                <div
                  className={`field-row ${selectedId && groupFields.some((f) => f.id === selectedId) ? "selected" : ""}`}
                  onClick={() => { if (pn) onFieldClick(pn); }}
                  style={{ cursor: "pointer" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div className="field-value">{pn?.value || "Unknown"}</div>
                    {confidenceBadge(avgConf)}
                  </div>
                  <div className="field-meta" style={{ gap: 6 }}>
                    {pkg && <span>{pkg.value}</span>}
                    {temp && <span>{temp.value}</span>}
                    <span>p.{pn?.page_number || groupFields[0].page_number}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); onToggleSection(groupId); }}
                      style={{ background: "none", border: "none", color: "#2563eb", cursor: "pointer", fontSize: 11, padding: 0 }}
                    >
                      {isExpanded ? "less" : "details"}
                    </button>
                  </div>
                </div>

                {/* Expanded: show all fields for this variant */}
                {isExpanded && (
                  <div style={{ marginLeft: 16, borderLeft: "2px solid #e0e0e0", paddingLeft: 8 }}>
                    {groupFields.map((f) => (
                      <div
                        key={f.id}
                        className={`field-row ${selectedId === f.id ? "selected" : ""}`}
                        onClick={() => onFieldClick(f)}
                        style={{ padding: "4px 8px" }}
                      >
                        <div style={{ fontSize: 11, color: "#888" }}>{VARIANT_LABELS[f.field_type] || f.field_type}</div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontSize: 12 }}>{f.value}</span>
                          {confidenceBadge(f.confidence)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Loose (non-table-linked) part info */}
      {loose.length > 0 && (
        <div className="field-group">
          <div className="field-group-title">
            Other Extracted Values ({loose.length})
            <button
              onClick={() => onToggleSection("__loose__")}
              style={{ background: "none", border: "none", color: "#2563eb", cursor: "pointer", fontSize: 11, padding: 0, marginLeft: 8 }}
            >
              {expandedSection === "__loose__" ? "hide" : "show"}
            </button>
          </div>
          {expandedSection === "__loose__" && loose
            .sort((a, b) => b.confidence - a.confidence)
            .map((f) => (
              <div key={f.id} className={`field-row ${selectedId === f.id ? "selected" : ""}`} onClick={() => onFieldClick(f)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ fontSize: 11, color: "#888" }}>{VARIANT_LABELS[f.field_type] || f.field_type}</div>
                  {confidenceBadge(f.confidence)}
                </div>
                <div className="field-value" style={{ fontSize: 12 }}>{f.value}</div>
                <div className="field-meta"><span>p.{f.page_number}</span></div>
              </div>
            ))}
        </div>
      )}
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
    <div style={{
      marginBottom: 16,
      border: isSelected ? "2px solid #2563eb" : "1px solid #e0e0e0",
      borderRadius: 8,
      overflow: "hidden",
    }}>
      <div onClick={onTableClick} style={{
        padding: "8px 12px", background: "#f8f9fa", borderBottom: "1px solid #e0e0e0",
        cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13,
      }}>
        <span style={{ fontWeight: 500 }}>Table {table.table_index + 1}</span>
        <span style={{ color: "#888", fontSize: 12 }}>p.{table.page_number} &middot; {table.row_count}&times;{table.col_count}</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <tbody>
            {grid.map((row, rIdx) => (
              <tr key={rIdx}>
                {row.map((cellText, cIdx) => {
                  const cellKey = `${table.id}-${rIdx}-${cIdx}`;
                  const isHeader = rIdx === 0 && table.headers.length > 0;
                  const isHovered = hoveredCell === cellKey;
                  return (
                    <td key={cIdx}
                      onMouseEnter={() => onCellHover(rIdx, cIdx)}
                      onMouseLeave={onCellLeave}
                      onClick={(e) => { e.stopPropagation(); onCellClick(rIdx, cIdx); }}
                      style={{
                        padding: "4px 8px", borderBottom: "1px solid #eee",
                        borderRight: cIdx < row.length - 1 ? "1px solid #eee" : undefined,
                        fontWeight: isHeader ? 600 : 400,
                        background: isHovered ? "#eef4ff" : isHeader ? "#f0f4f8" : undefined,
                        cursor: "pointer", whiteSpace: "nowrap", maxWidth: 200,
                        overflow: "hidden", textOverflow: "ellipsis",
                      }}
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
