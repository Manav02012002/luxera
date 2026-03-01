import type { JsonRow } from "../types";

export function scalarText(value: unknown): string {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(Math.abs(value) >= 100 ? 1 : 3) : "NaN";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "-";
  }
  return JSON.stringify(value);
}

export function objectToRows(obj: JsonRow | null | undefined): JsonRow[] {
  if (!obj) {
    return [];
  }
  return Object.entries(obj).map(([key, value]) => ({ key, value: scalarText(value) }));
}

export function flattenJsonRows(root: unknown, rootLabel: string, maxRows = 5000): JsonRow[] {
  const rows: JsonRow[] = [];
  const queue: Array<{ value: unknown; path: string }> = [{ value: root, path: rootLabel }];
  while (queue.length > 0 && rows.length < maxRows) {
    const item = queue.shift();
    if (!item) {
      break;
    }
    const { value, path } = item;
    if (Array.isArray(value)) {
      rows.push({ path, type: "array", size: value.length, value: "" });
      value.forEach((entry, idx) => queue.push({ value: entry, path: `${path}[${idx}]` }));
      continue;
    }
    if (value !== null && typeof value === "object") {
      const rec = value as Record<string, unknown>;
      rows.push({ path, type: "object", size: Object.keys(rec).length, value: "" });
      for (const [k, v] of Object.entries(rec)) {
        queue.push({ value: v, path: `${path}.${k}` });
      }
      continue;
    }
    rows.push({ path, type: typeof value, size: "", value: scalarText(value) });
  }
  return rows;
}

export function asFiniteNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) {
      return n;
    }
  }
  return undefined;
}

export function firstNumeric(row: JsonRow | null | undefined, keys: string[]): number | undefined {
  if (!row) {
    return undefined;
  }
  for (const key of keys) {
    const v = asFiniteNumber(row[key]);
    if (v !== undefined) {
      return v;
    }
  }
  return undefined;
}

export type Point2 = { x: number; y: number; label: string };

export function rowsToPoints(rows: JsonRow[]): Point2[] {
  const out: Point2[] = [];
  for (const row of rows) {
    const x = firstNumeric(row, ["x", "observer_x", "point_x"]);
    const y = firstNumeric(row, ["y", "observer_y", "point_y", "lane_number"]);
    if (x === undefined || y === undefined) {
      continue;
    }
    const label = (typeof row.id === "string" && row.id) || (typeof row.name === "string" && row.name) || "row";
    out.push({ x, y, label });
  }
  return out;
}
