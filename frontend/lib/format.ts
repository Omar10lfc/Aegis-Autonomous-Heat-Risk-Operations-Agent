/**
 * Human-readable formatting for Aegis UI.
 * Converts internal snake_case identifiers to clean display labels.
 */

// Known prefix expansions
const PREFIX_MAP: Record<string, string> = {
  phx: "Phoenix",
  lax: "Los Angeles",
  dfw: "Dallas-Fort Worth",
  atl: "Atlanta",
  ord: "Chicago",
};

// Known word expansions
const WORD_MAP: Record<string, string> = {
  env: "Environmental",
  params: "Parameters",
  crossdock: "Crossdock",
  heatmap: "Heatmap",
  aoi: "AOI",
  api: "API",
  tcm: "TCM",
  id: "ID",
};

// Metric label overrides
const METRIC_MAP: Record<string, string> = {
  hours_above_threshold: "Hours Above Threshold",
  longest_sustained_hours: "Longest Sustained Hours",
  peak_temp_celsius: "Peak Temperature",
  heat_index_celsius: "Heat Index",
  value: "Value",
};

// Unit display
const UNIT_MAP: Record<string, string> = {
  hour: "hr",
  hours: "hr",
  celsius: "°C",
  fahrenheit: "°F",
  mi2: "mi²",
  km2: "km²",
};

/**
 * Convert a snake_case site label to a human-readable name.
 * "phx_southwest_freight" → "Phoenix Southwest Freight"
 * "phx_sky_harbor_yard"   → "Phoenix Sky Harbor Yard"
 * "phx_deer_valley"       → "Phoenix Deer Valley"
 */
export function prettifyLabel(raw: string): string {
  if (!raw) return raw;

  // Strip trailing "-env" suffix (env_params jobs append it)
  const base = raw.replace(/-env$/, "");
  const parts = base.split("_");
  const result: string[] = [];

  for (let i = 0; i < parts.length; i++) {
    const token = parts[i].toLowerCase();
    // First token: try prefix expansion
    if (i === 0 && PREFIX_MAP[token]) {
      result.push(PREFIX_MAP[token]);
      continue;
    }
    // Known word expansion
    if (WORD_MAP[token]) {
      result.push(WORD_MAP[token]);
      continue;
    }
    // Title-case the word
    result.push(token.charAt(0).toUpperCase() + token.slice(1));
  }

  return result.join(" ");
}

/**
 * Convert a metric field name to human-readable.
 * "hours_above_threshold" → "Hours Above Threshold"
 */
export function prettifyMetric(raw: string | null | undefined): string {
  if (!raw) return "";
  if (METRIC_MAP[raw]) return METRIC_MAP[raw];
  return raw
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Format a numeric value with its unit.
 * formatValue(13.6, "hour") → "13.6 hr"
 * formatValue(44.6, "celsius") → "44.6 °C"
 */
export function formatValue(
  value: number | null | undefined,
  units?: string | null
): string {
  if (value === null || value === undefined) return "—";
  const v = typeof value === "number" ? value : Number(value);
  if (isNaN(v)) return String(value);
  const u = units ? UNIT_MAP[units.toLowerCase()] ?? units : "";
  return u ? `${v}${u.startsWith("°") ? "" : " "}${u}` : String(v);
}

/**
 * Extract a short display ID from a full activity_id / cache key.
 * "cached-heatmap-phx_sky_harbor_yard-0a50624f" → "0a50624f"
 * "cached-env-phx_deer_valley-env-07329a61"     → "07329a61"
 * null → "—"
 */
export function truncateId(raw: string | null | undefined): string {
  if (!raw) return "—";
  const parts = raw.split("-");
  const last = parts[parts.length - 1];
  if (/^[0-9a-f]{6,}$/i.test(last)) return last.slice(0, 8);
  return raw.length > 12 ? `…${raw.slice(-12)}` : raw;
}

/**
 * Clean up a FortyGuard endpoint path for display.
 * "/v1/heatmap"    → "Heatmap API"
 * "/v1/env_params" → "Env Parameters API"
 * "/v1/system/fetch-api-key-usage" → "System API"
 */
export function prettifyEndpoint(raw: string): string {
  if (!raw) return "";
  if (raw.includes("heatmap")) return "Heatmap API";
  if (raw.includes("env_params")) return "Env Parameters API";
  if (raw.includes("system")) return "System API";
  if (raw.includes("status")) return "Status API";
  return raw;
}

/**
 * Post-process memo markdown to replace raw identifiers with human-readable text.
 */
export function cleanMemoMarkdown(md: string): string {
  if (!md) return "";
  let out = md;

  // 1. Remove raw API cache keys, endpoints, and messy brackets inside the text:
  // e.g. (; `/v1/heatmap` `cached-heatmap-...`) or (; /v1/heatmap cached-heatmap-...)
  out = out.replace(/;\s*[`'"]?\/?v1\/(?:heatmap|env_params)[`'"]?\s*[`'"]?cached[-_](?:heatmap|env)[-_][a-zA-Z0-9_-]+[`'"]?/gi, "");
  out = out.replace(/[`'"]?cached[-_](?:heatmap|env)[-_][a-zA-Z0-9_-]+[`'"]?/gi, "");
  out = out.replace(/;\s*[`'"]?\/v1\/[a-zA-Z0-9_\/-]+[`'"]?/gi, "");

  // 2. Clean up empty/dangling parentheses or brackets
  out = out.replace(/\(\s*;\s*\)/g, "");
  out = out.replace(/\(\s*mean=([^;)]+)\s*;\s*\)/g, "(mean: $1)");
  out = out.replace(/\(\s*mean=([^;)]+)\s*\)/g, "(mean: $1)");

  // 3. Clean up "analytic_type" references & Analysis Layer text
  out = out.replace(/\(analytic_type mapped from FortyGuard heatmap\)/gi, "(FortyGuard Temperature API)");
  out = out.replace(/\(analysis type mapped from FortyGuard heatmap\)/gi, "(FortyGuard Temperature API)");
  out = out.replace(/\(analysis type mapped from FortyGuard heatmap data\)/gi, "(FortyGuard Temperature API)");
  out = out.replace(/\*\*Analysis layer:\*\*\s*([a-z]+)/gi, (_, layer) => `**Analysis Layer:** ${layer.charAt(0).toUpperCase() + layer.slice(1)}`);

  // 4. Prettify site labels safely without double-wrapping in ** or breaking existing markdown
  // Match `phx_xxx_yyy` or **phx_xxx_yyy** or `phx_xxx_yyy`
  out = out.replace(/(\*\*)?(?:`|')?(phx|lax|dfw|atl|ord)(_[a-z0-9]+){1,6}(?:`|')?(\*\*)?/gi, (match) => {
    // Extract the raw token
    const raw = match.replace(/[\*`']/g, "");
    return `**${prettifyLabel(raw)}**`;
  });

  // 5. Clean up metric equations: e.g. hours_above_threshold=13.6 hour -> 13.6 hr hours above threshold
  out = out.replace(/hours_above_threshold=([0-9.]+)\s*(hour|hr)?/gi, "$1 hr hours above threshold");
  out = out.replace(/longest_sustained_hours=([0-9.]+)\s*(hour|hr)?/gi, "$1 hr longest sustained hours");
  out = out.replace(/peak_temp_celsius=([0-9.]+)\s*(celsius|°C)?/gi, "$1 °C peak temperature");
  out = out.replace(/heat_index_celsius=([0-9.]+)\s*(celsius|°C)?/gi, "$1 °C heat index");

  // 6. Clean up plain metric names
  out = out.replace(/hours_above_threshold/gi, "hours above threshold");
  out = out.replace(/longest_sustained_hours/gi, "longest sustained hours");
  out = out.replace(/peak_temp_celsius/gi, "peak temperature");
  out = out.replace(/heat_index_celsius/gi, "heat index");

  // 7. Normalize whitespace & quotes
  out = out.replace(/ {2,}/g, " ");
  out = out.replace(/\(\s*\)/g, "");

  return out;
}

/**
 * Compute risk severity level grouped by metric type/field so temperatures
 * (44-47 °C) and hours (8-13 hr) are independently normalized.
 */
export function riskLevelByMetric(
  value: number | null,
  field: string,
  allCitations: { value: number | null; field: string }[]
): "high" | "medium" | "low" {
  if (value === null || value === undefined) return "low";

  // Filter citations belonging to the same field/metric
  const sameMetricValues = allCitations
    .filter((c) => c.field === field && c.value !== null)
    .map((c) => c.value as number);

  if (sameMetricValues.length === 0) return "medium";

  const sorted = [...sameMetricValues].sort((a, b) => b - a);
  const max = sorted[0];
  const min = sorted[sorted.length - 1];

  if (max === min) return "medium";

  const idx = sorted.indexOf(value);
  const percentile = idx / sorted.length;

  if (percentile <= 0.33) return "high";
  if (percentile <= 0.66) return "medium";
  return "low";
}
