import { useMemo, useState } from "react";
import type { JsonRow } from "../types";
import { scalarText } from "../utils/table";

type SortDir = "asc" | "desc";

interface DataTableProps {
  title: string;
  rows: JsonRow[];
  onSelectRow?: (title: string, row: JsonRow, index: number) => void;
  selectedTableTitle?: string;
  selectedRowIndex?: number;
}

export function DataTable({ title, rows, onSelectRow, selectedTableTitle, selectedRowIndex }: DataTableProps) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const columns = useMemo(() => {
    const keys = new Set<string>();
    for (const row of rows) {
      for (const key of Object.keys(row)) {
        keys.add(key);
      }
    }
    return Array.from(keys);
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (!query.trim()) {
      return rows;
    }
    const q = query.trim().toLowerCase();
    return rows.filter((row) => Object.values(row).some((v) => scalarText(v).toLowerCase().includes(q)));
  }, [rows, query]);

  const orderedRows = useMemo(() => {
    if (!sortKey) {
      return filteredRows;
    }
    const out = [...filteredRows];
    out.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const an = typeof av === "number" ? av : Number.NaN;
      const bn = typeof bv === "number" ? bv : Number.NaN;
      if (Number.isFinite(an) && Number.isFinite(bn)) {
        return sortDir === "asc" ? an - bn : bn - an;
      }
      const as = scalarText(av).toLowerCase();
      const bs = scalarText(bv).toLowerCase();
      if (as < bs) {
        return sortDir === "asc" ? -1 : 1;
      }
      if (as > bs) {
        return sortDir === "asc" ? 1 : -1;
      }
      return 0;
    });
    return out;
  }, [filteredRows, sortDir, sortKey]);

  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir("asc");
  };

  const selectable = typeof onSelectRow === "function";

  return (
    <section className="rounded-md border border-border bg-panel p-3">
      <div className="mb-2 text-xs uppercase tracking-[0.12em] text-muted">
        {title} ({orderedRows.length}/{rows.length})
      </div>
      <div className="mb-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter rows..."
          className="w-full rounded border border-border bg-panelSoft/50 px-2 py-1 text-xs text-text outline-none focus:ring-2 focus:ring-blue-400/30"
        />
      </div>
      {rows.length === 0 ? (
        <div className="rounded border border-border/60 bg-panelSoft/50 px-2 py-1 text-xs text-muted">No rows.</div>
      ) : (
        <div className="max-h-56 overflow-auto rounded border border-border/60">
          <table className="min-w-full text-xs">
            <thead className="sticky top-0 bg-panel">
              <tr>
                {columns.map((col) => (
                  <th key={col} className="border-b border-border/70 px-2 py-1 text-left font-semibold text-muted">
                    <button type="button" className="text-left" onClick={() => toggleSort(col)}>
                      {col}
                      {sortKey === col ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orderedRows.map((row, idx) => (
                <tr
                  key={`${title}-${idx}`}
                  className={`odd:bg-panelSoft/30 ${selectable ? "cursor-pointer hover:bg-blue-900/20" : ""} ${
                    selectedTableTitle === title && selectedRowIndex === idx ? "bg-blue-900/30 ring-1 ring-blue-400/40" : ""
                  }`}
                  onClick={() => {
                    if (onSelectRow) {
                      onSelectRow(title, row, idx);
                    }
                  }}
                >
                  {columns.map((col) => (
                    <td key={`${title}-${idx}-${col}`} className="border-b border-border/50 px-2 py-1 align-top text-text">
                      {scalarText(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
