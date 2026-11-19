/** Copies each column header's text onto its body cells as `data-label`, so tables can collapse into stacked cards on phones. */
export function labelTables(root: ParentNode): void {
  root.querySelectorAll<HTMLTableElement>("table.table").forEach((table) => {
    const heads = Array.from(table.querySelectorAll<HTMLTableCellElement>("thead th")).map((th) => th.dataset.label ?? ((th.textContent ?? "").trim() || th.getAttribute("aria-label") || ""));
    table.querySelectorAll<HTMLTableRowElement>("tbody tr").forEach((tr) => {
      Array.from(tr.cells).forEach((td, i) => {
        const label = heads[i] ?? "";
        if (td.getAttribute("data-label") !== label) td.setAttribute("data-label", label);
      });
    });
  });
}

/** Keeps `data-label` in sync while React re-renders tables under `root`. */
export function observeTableLabels(root: HTMLElement): () => void {
  let frame = 0;
  const run = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => labelTables(root)); };
  labelTables(root);
  const mo = new MutationObserver(run);
  mo.observe(root, { childList: true, subtree: true, characterData: true });
  return () => { cancelAnimationFrame(frame); mo.disconnect(); };
}
