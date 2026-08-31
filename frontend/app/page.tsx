"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import PipelineBar from "../components/PipelineBar";
import type { MapSite } from "../components/SiteMap";
import {
  getReport,
  getStatus,
  submitBrief,
  type Citation,
  type Report,
} from "../lib/api";
import {
  prettifyLabel,
  prettifyMetric,
  formatValue,
  prettifyEndpoint,
  truncateId,
  cleanMemoMarkdown,
  riskLevelByMetric,
} from "../lib/format";
import { captureMapCanvas, exportReportPdf } from "../lib/pdf";

// MapLibre touches window at import time; load it client-side only.
const MapInner = dynamic(() => import("../components/SiteMap"), { ssr: false });

const EXAMPLE =
  "Which of our Phoenix distribution routes crossed dangerous heat thresholds last month, and where should we reroute?";

/* ── Markdown renderer ── */

function renderMarkdown(md: string): React.ReactNode[] {
  const cleaned = cleanMemoMarkdown(md);
  return cleaned.split("\n").map((line, i) => {
    if (line.startsWith("### ")) return <h3 key={i}>{inline(line.slice(4))}</h3>;
    if (line.startsWith("## ")) return <h2 key={i}>{inline(line.slice(3))}</h2>;
    if (line.startsWith("# ")) return <h1 key={i}>{inline(line.slice(2))}</h1>;
    if (/^\s*[-*] /.test(line))
      return <li key={i}>{inline(line.replace(/^\s*[-*] /, ""))}</li>;
    const m = line.match(/^\s*(\d+)\. (.*)$/);
    if (m) return <li key={i}>{inline(m[2])}</li>;
    if (!line.trim()) return null;
    return <p key={i}>{inline(line)}</p>;
  });
}

function inline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      const inner = part.slice(2, -2).replace(/^\*\*|\*\*$/g, "");
      return <strong key={i}>{inner}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`"))
      return <code key={i}>{part.slice(1, -1)}</code>;
    return part;
  });
}

/* ── Site extraction ── */

function sitesFromReport(report: Report): MapSite[] {
  const jobs = report.plan?.heatmap_jobs ?? [];
  const byLabel = new Map<string, Citation>();
  for (const c of report.citations) {
    if (!byLabel.has(c.label)) byLabel.set(c.label, c);
  }
  const heatmapAudit = new Map<
    string,
    { activityId: string | null; mean: number | null }
  >();
  report.audit_trail
    .filter((a) => a.endpoint === "/v1/heatmap" && a.status === "succeeded")
    .forEach((a) => {
      const stats = a.result?.stats_data;
      heatmapAudit.set(a.label, {
        activityId: a.activity_id,
        mean: stats?.mean ?? null,
      });
    });
  const sites: MapSite[] = [];
  jobs.forEach((job) => {
    const cite = byLabel.get(job.label);
    const ring = job.polygon_aoi?.features?.[0]?.geometry?.coordinates?.[0];
    if (!ring || !cite) return;
    const audit = heatmapAudit.get(job.label);
    sites.push({
      label: job.label,
      rank: sites.length,
      value: cite.value,
      metric: cite.field,
      ring,
      endpoint: cite.endpoint,
      activity_id: audit?.activityId ?? cite.activity_id ?? null,
      mean: audit?.mean ?? null,
      units: cite.units ?? null,
    });
  });
  return sites;
}

/* ── Main component ── */

export default function Home() {
  const [brief, setBrief] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [traceUrl, setTraceUrl] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lastBrief = useRef<string>("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const poll = useCallback(async (id: string) => {
    try {
      const s = await getStatus(id);
      setStage(s.stage);
      setTraceUrl(s.langsmith_url);
      setStatus(s.status);
      if (s.status === "succeeded") {
        setReport(await getReport(id));
        setBusy(false);
        return;
      }
      if (s.status === "failed") {
        try {
          const r = await getReport(id);
          if (r.markdown) {
            setReport(r);
            setStatus("succeeded");
            setBusy(false);
            return;
          }
        } catch {
          // ignore
        }
        setError(s.error ?? "pipeline failed");
        setBusy(false);
        return;
      }
      timer.current = setTimeout(() => poll(id), 1500);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function handleSubmit(briefText: string) {
    setError(null);
    setReport(null);
    setTraceUrl(null);
    setStatus("queued");
    setStage(null);
    setBusy(true);
    lastBrief.current = briefText;
    try {
      const accepted = await submitBrief(briefText);
      setJobId(accepted.job_id);
      if (accepted.status === "succeeded") {
        // Vercel sync path: job already completed, fetch report directly
        setStatus("succeeded");
        setStage("complete");
        setReport(await getReport(accepted.job_id));
        setBusy(false);
      } else if (accepted.status === "failed") {
        try {
          const r = await getReport(accepted.job_id);
          if (r.markdown) {
            setReport(r);
            setStatus("succeeded");
            setBusy(false);
            return;
          }
        } catch {
          // fallback to error state
        }
        setError("Pipeline execution failed");
        setStatus("failed");
        setBusy(false);
      } else {
        await poll(accepted.job_id);
      }
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    handleSubmit(brief);
  }

  function onRetry() {
    if (lastBrief.current) handleSubmit(lastBrief.current);
  }

  const sites = report ? sitesFromReport(report) : [];

  const [exportingPdf, setExportingPdf] = useState(false);

  async function downloadPdf() {
    if (!report) return;
    setExportingPdf(true);
    try {
      const mapDataUrl = captureMapCanvas(sites);
      await exportReportPdf(report, sites, mapDataUrl);
    } catch (err) {
      console.error("[PDF] Export failed:", err);
    } finally {
      setExportingPdf(false);
    }
  }

  function downloadMemoTxt() {
    if (!report) return;
    const plain = cleanMemoMarkdown(report.markdown)
      .replace(/^#{1,3} /gm, "")
      .replace(/\*\*|\*/g, "")
      .replace(/`/g, "")
      .replace(/^\s*[-*] /gm, "- ");
    const blob = new Blob([plain], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aegis-memo-${report.job_id.slice(0, 8)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Compute summary stats
  const highestSite = sites.length > 0
    ? sites.reduce((a, b) =>
        (a.value ?? 0) >= (b.value ?? 0) ? a : b
      )
    : null;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          Aegis<span>.</span>
        </div>
        <div className="tagline">
          Street-level heat risk, ranked and cited. FortyGuard Temperature API.
        </div>
      </header>

      <div className="grid">
        <section className="panel">
          <h1 className="sr-only">Aegis Heat Risk Agent</h1>
          <h2>Operations brief</h2>
          <form onSubmit={onSubmit} id="brief-form">
            <textarea
              id="brief-input"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder={EXAMPLE}
              aria-label="Operations brief"
            />
            <div className="actions">
              <button
                id="run-btn"
                type="submit"
                className="primary"
                disabled={busy || brief.trim().length < 8}
              >
                {busy ? "Working…" : "Run agent"}
              </button>
              <button
                id="example-btn"
                type="button"
                className="ghost"
                onClick={() => setBrief(EXAMPLE)}
                disabled={busy}
              >
                Example brief
              </button>
            </div>
          </form>

          {(status === "running" || status === "queued" || report) && (
            <PipelineBar stage={stage} status={status} />
          )}

          {status !== "idle" && (
            <div className={`status ${status === "failed" ? "failed" : ""}`}>
              <span className="meta">
                <code>{jobId?.slice(0, 8)}</code>{" "}
                <strong>{status === "succeeded" ? "Complete" : status}</strong>
                {report?.planner_model
                  ? ` · ${report.planner_model.split(":").pop()}`
                  : ""}
                {report?.fortyguard_mode
                  ? ` · ${report.fortyguard_mode} data`
                  : ""}
              </span>
              {traceUrl && (
                <a
                  className="trace"
                  href={traceUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  LangSmith trace ↗
                </a>
              )}
            </div>
          )}

          {error && (
            <div className="error-block">
              <p className="error-text">Error: {error}</p>
              <button
                id="retry-btn"
                type="button"
                className="ghost"
                onClick={onRetry}
                disabled={busy || !lastBrief.current}
              >
                Retry
              </button>
            </div>
          )}
        </section>

        <section className="map-wrap" aria-label="Site map">
          <MapInner sites={sites} />
        </section>
      </div>

      {/* ── Summary cards ── */}
      {report && sites.length > 0 && (
        <div className="summary-cards">
          <div className="summary-card">
            <span className="summary-label">Sites Analyzed</span>
            <span className="summary-value">{sites.length}</span>
          </div>
          <div className="summary-card accent">
            <span className="summary-label">Highest Risk</span>
            <span className="summary-value">
              {highestSite ? prettifyLabel(highestSite.label) : "—"}
            </span>
            {highestSite && (
              <span className="summary-sub">
                {formatValue(highestSite.value, highestSite.units)} ·{" "}
                {prettifyMetric(highestSite.metric)}
              </span>
            )}
          </div>
          <div className="summary-card">
            <span className="summary-label">Analysis</span>
            <span className="summary-value">
              {report.plan
                ? prettifyMetric(
                    report.plan.analysis_layer ||
                      report.plan.heatmap_jobs?.[0]?.analytic_type ||
                      "exceedance"
                  )
                : "—"}
            </span>
          </div>
        </div>
      )}

      {/* ── Report ── */}
      {report && (
        <div className="report">
          <section className="panel memo">
            <div className="panel-head">
              <h2>Operations Memo</h2>
              <div className="actions">
                <button
                  id="export-pdf-btn"
                  type="button"
                  className="ghost"
                  onClick={downloadPdf}
                  disabled={exportingPdf}
                  title="Download complete report with map as PDF"
                >
                  {exportingPdf ? "Generating PDF…" : "Export .pdf"}
                </button>
                <button
                  id="export-txt-btn"
                  type="button"
                  className="ghost"
                  onClick={downloadMemoTxt}
                  title="Download plain-text memo"
                >
                  Export .txt
                </button>
              </div>
            </div>
            <div className="memo-body">
              {renderMarkdown(report.markdown)}
            </div>
          </section>

          <section className="panel">
            <h2>Citations</h2>
            <div className="citation-list">
              {report.citations.map((c, i) => {
                const risk = riskLevelByMetric(c.value, c.field, report.citations);
                return (
                  <div key={i} className={`citation-card risk-${risk}`}>
                    <div className="citation-header">
                      <span className={`risk-badge ${risk}`}>{risk}</span>
                      <strong className="citation-name">
                        {prettifyLabel(c.label)}
                      </strong>
                    </div>
                    <div className="citation-metric">
                      {prettifyMetric(c.field)}:{" "}
                      <strong>{formatValue(c.value, c.units)}</strong>
                    </div>
                    <div className="citation-source">
                      <span className="citation-endpoint">{prettifyEndpoint(c.endpoint)}</span>
                      {c.activity_id && (
                        <>
                          {" "}·{" "}
                          <code>{truncateId(c.activity_id)}</code>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            {report.langsmith_url && (
              <p style={{ marginTop: 16 }}>
                <a
                  className="trace"
                  href={report.langsmith_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Full run trace ↗
                </a>
              </p>
            )}
          </section>
        </div>
      )}

      {/* ── Audit trail ── */}
      {report && report.audit_trail.length > 0 && (
        <section className="panel audit">
          <h2>Data Audit Trail</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Site</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Tries</th>
                  <th>Activity ID</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {report.audit_trail.map((c, i) => (
                  <tr key={i}>
                    <td className="site-name">{prettifyLabel(c.label)}</td>
                    <td className="mono">
                      {prettifyEndpoint(c.endpoint)}
                    </td>
                    <td>
                      <span
                        className={`audit-status ${c.status === "succeeded" ? "ok" : c.status === "failed" ? "failed" : ""}`}
                      >
                        {c.status === "succeeded"
                          ? "✓ OK"
                          : c.status === "failed"
                            ? "✗ Failed"
                            : c.status}
                      </span>
                    </td>
                    <td>{c.attempts}</td>
                    <td className="mono id">
                      {truncateId(c.activity_id)}
                    </td>
                    <td className="err-col">{c.error ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
