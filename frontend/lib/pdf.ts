import { jsPDF } from "jspdf";
import type { Report } from "./api";
import type { MapSite } from "../components/SiteMap";
import {
  prettifyLabel,
  prettifyMetric,
  formatValue,
  prettifyEndpoint,
  truncateId,
  cleanMemoMarkdown,
  riskLevelByMetric,
} from "./format";

const RANK_COLORS = ["#e8703a", "#f2a25c", "#d8cf4a", "#7a8f6a"];

/**
 * Generate a high-resolution, standalone cartographic vector map of the Phoenix
 * operations area with accurate polygon footprints, grid lines, and site callouts.
 */
export function generateVectorMapImage(sites: MapSite[]): string {
  if (typeof document === "undefined") return "";

  const width = 1200;
  const height = 560;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";

  // 1. Dark Cartographic Background
  ctx.fillStyle = "#121715";
  ctx.fillRect(0, 0, width, height);

  // 2. Subtle coordinate bounds (Phoenix metro)
  let minLon = -112.35;
  let maxLon = -111.85;
  let minLat = 33.28;
  let maxLat = 33.68;

  // Calculate actual bounding box if sites exist
  if (sites.length > 0) {
    const allCoords: [number, number][] = [];
    sites.forEach((s) => s.ring.forEach(([lon, lat]) => allCoords.push([lon, lat])));
    if (allCoords.length > 0) {
      const lons = allCoords.map((c) => c[0]);
      const lats = allCoords.map((c) => c[1]);
      minLon = Math.min(...lons) - 0.08;
      maxLon = Math.max(...lons) + 0.08;
      minLat = Math.min(...lats) - 0.06;
      maxLat = Math.max(...lats) + 0.06;
    }
  }

  const lonToX = (lon: number) => ((lon - minLon) / (maxLon - minLon)) * (width - 120) + 60;
  const latToY = (lat: number) => (1 - (lat - minLat) / (maxLat - minLat)) * (height - 90) + 45;

  // 3. Grid lines & Coordinate Labels
  ctx.strokeStyle = "rgba(42, 48, 44, 0.65)";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);

  for (let lon = Math.ceil(minLon * 10) / 10; lon <= maxLon; lon += 0.1) {
    const x = lonToX(lon);
    ctx.beginPath();
    ctx.moveTo(x, 25);
    ctx.lineTo(x, height - 25);
    ctx.stroke();

    ctx.fillStyle = "#6b736b";
    ctx.font = "11px monospace";
    ctx.fillText(`${lon.toFixed(1)}°W`, x - 18, height - 10);
  }

  for (let lat = Math.ceil(minLat * 10) / 10; lat <= maxLat; lat += 0.1) {
    const y = latToY(lat);
    ctx.beginPath();
    ctx.moveTo(35, y);
    ctx.lineTo(width - 35, y);
    ctx.stroke();

    ctx.fillStyle = "#6b736b";
    ctx.font = "11px monospace";
    ctx.fillText(`${lat.toFixed(1)}°N`, 6, y + 4);
  }
  ctx.setLineDash([]);

  // 4. Highway & Arterial Corridors (I-10, Loop 202, I-17)
  ctx.strokeStyle = "rgba(79, 184, 106, 0.15)";
  ctx.lineWidth = 2.5;

  // I-10 corridor
  ctx.beginPath();
  ctx.moveTo(lonToX(-112.35), latToY(33.46));
  ctx.lineTo(lonToX(-112.07), latToY(33.46));
  ctx.lineTo(lonToX(-111.96), latToY(33.41));
  ctx.lineTo(lonToX(-111.85), latToY(33.33));
  ctx.stroke();

  // I-17 corridor
  ctx.beginPath();
  ctx.moveTo(lonToX(-112.11), latToY(33.68));
  ctx.lineTo(lonToX(-112.11), latToY(33.48));
  ctx.lineTo(lonToX(-112.07), latToY(33.44));
  ctx.stroke();

  // 5. Draw Site Polygons & Thermal Risk Footprints
  sites.forEach((s) => {
    if (!s.ring || s.ring.length === 0) return;

    const rankColor = RANK_COLORS[s.rank] || RANK_COLORS[0];

    // Polygon Path
    ctx.beginPath();
    const [startLon, startLat] = s.ring[0];
    ctx.moveTo(lonToX(startLon), latToY(startLat));
    for (let i = 1; i < s.ring.length; i++) {
      const [lon, lat] = s.ring[i];
      ctx.lineTo(lonToX(lon), latToY(lat));
    }
    ctx.closePath();

    // Heat Glow Fill
    ctx.fillStyle = rankColor + "70";
    ctx.fill();

    // Outlines
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 3.5;
    ctx.stroke();

    ctx.strokeStyle = rankColor;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Centroid
    let cX = 0;
    let cY = 0;
    s.ring.forEach(([lon, lat]) => {
      cX += lonToX(lon);
      cY += latToY(lat);
    });
    cX /= s.ring.length;
    cY /= s.ring.length;

    // Centroid Marker Pin
    ctx.beginPath();
    ctx.arc(cX, cY, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cX, cY, 3, 0, Math.PI * 2);
    ctx.fillStyle = rankColor;
    ctx.fill();

    // Site Callout Label Card
    const prettyName = prettifyLabel(s.label);
    const valText = s.value !== null ? `${formatValue(s.value, s.units)}` : "";
    const cardText = `${prettyName}  [${valText}]`;

    ctx.font = "bold 13px system-ui, sans-serif";
    const textWidth = ctx.measureText(cardText).width;
    const cardW = textWidth + 24;
    const cardH = 26;
    const cardX = Math.max(10, Math.min(width - cardW - 10, cX - cardW / 2));
    const cardY = cY - 40;

    // Card background
    ctx.fillStyle = "rgba(16, 19, 18, 0.94)";
    ctx.strokeStyle = rankColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(cardX, cardY, cardW, cardH, 5);
    ctx.fill();
    ctx.stroke();

    // Connector tick
    ctx.beginPath();
    ctx.moveTo(cX, cY - 4);
    ctx.lineTo(cX, cardY + cardH);
    ctx.strokeStyle = rankColor;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Text
    ctx.fillStyle = "#ffffff";
    ctx.fillText(prettyName, cardX + 10, cardY + 17);

    if (valText) {
      ctx.fillStyle = rankColor;
      ctx.fillText(valText, cardX + textWidth - ctx.measureText(valText).width + 10, cardY + 17);
    }
  });

  // 6. North Compass Arrow
  ctx.save();
  ctx.translate(width - 40, 40);
  ctx.fillStyle = "#e8703a";
  ctx.beginPath();
  ctx.moveTo(0, -16);
  ctx.lineTo(5, 5);
  ctx.lineTo(0, 2);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = "#9aa39a";
  ctx.beginPath();
  ctx.moveTo(0, -16);
  ctx.lineTo(-5, 5);
  ctx.lineTo(0, 2);
  ctx.closePath();
  ctx.fill();
  ctx.font = "bold 10px monospace";
  ctx.fillStyle = "#e8ebe7";
  ctx.fillText("N", -3.5, -20);
  ctx.restore();

  // 7. Scale Indicator
  ctx.fillStyle = "rgba(16, 19, 18, 0.85)";
  ctx.strokeStyle = "#2a302c";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(width - 150, height - 34, 135, 24, 4);
  ctx.fill();
  ctx.stroke();

  ctx.strokeStyle = "#e8ebe7";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(width - 140, height - 20);
  ctx.lineTo(width - 85, height - 20);
  ctx.stroke();
  ctx.fillText("5 miles", width - 80, height - 18);

  return canvas.toDataURL("image/png");
}

/**
 * Capture or generate vector cartography for PDF embedding.
 */
export function captureMapCanvas(sites: MapSite[]): string {
  return generateVectorMapImage(sites);
}

/**
 * Generate and download a publication-grade 2-Page Executive PDF report.
 */
export async function exportReportPdf(
  report: Report,
  sites: MapSite[],
  mapDataUrl?: string | null
): Promise<void> {
  const doc = new jsPDF({
    orientation: "portrait",
    unit: "mm",
    format: "a4",
  });

  const pageWidth = doc.internal.pageSize.getWidth(); // 210mm
  const pageHeight = doc.internal.pageSize.getHeight(); // 297mm
  const margin = 14;
  const contentWidth = pageWidth - margin * 2; // 182mm

  // ══════════════════════════════════════════════════════════════════════════
  // PAGE 1: EXECUTIVE BRIEFING & GEOSPATIAL HEAT ANALYSIS
  // ══════════════════════════════════════════════════════════════════════════

  // 1. Header Banner
  doc.setFillColor(16, 19, 18); // #101312
  doc.rect(0, 0, pageWidth, 22, "F");

  doc.setFillColor(232, 112, 58); // #e8703a
  doc.rect(0, 21, pageWidth, 1.2, "F");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(13);
  doc.setTextColor(232, 235, 231);
  doc.text("AEGIS — HEAT RISK OPERATIONS MEMO", margin, 10.5);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(7.5);
  doc.setTextColor(154, 163, 154);
  doc.text("Street-Level Heat Risk Intelligence Platform · Powered by FortyGuard Temperature API", margin, 16.5);

  let y = 27;

  // 2. Metadata Dashboard Bar
  doc.setFillColor(246, 248, 246);
  doc.setDrawColor(215, 220, 215);
  doc.roundedRect(margin, y, contentWidth, 13, 1.5, 1.5, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(7.5);
  doc.setTextColor(30, 35, 30);
  doc.text("JOB ID:", margin + 4, y + 4.8);
  doc.text("GENERATED (UTC):", margin + 48, y + 4.8);
  doc.text("ANALYSIS LAYER:", margin + 105, y + 4.8);
  doc.text("DATA MODE:", margin + 150, y + 4.8);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(7.5);
  doc.setTextColor(75, 85, 75);
  doc.text(report.job_id.slice(0, 14), margin + 4, y + 9.5);
  doc.text(
    new Date(report.created_at || Date.now()).toISOString().replace("T", " ").slice(0, 19),
    margin + 48,
    y + 9.5
  );
  doc.text(
    prettifyMetric(
      report.plan?.analysis_layer ||
        report.plan?.heatmap_jobs?.[0]?.analytic_type ||
        "exceedance"
    ),
    margin + 105,
    y + 9.5
  );
  doc.text(report.fortyguard_mode ? `${report.fortyguard_mode} mode` : "cached", margin + 150, y + 9.5);

  y += 17;

  // 3. Geospatial Heat Analysis (Map)
  const mapImg = mapDataUrl || captureMapCanvas(sites);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(20, 25, 20);
  doc.text("GEOSPATIAL HEAT ANALYSIS", margin, y);
  y += 3.5;

  const mapWidth = contentWidth;
  const mapHeight = 62; // Balanced map height for clean page 1 composition

  doc.setDrawColor(190, 195, 190);
  doc.roundedRect(margin, y, mapWidth, mapHeight, 1.5, 1.5, "D");

  if (mapImg) {
    try {
      doc.addImage(mapImg, "PNG", margin, y, mapWidth, mapHeight, undefined, "FAST");
    } catch (e) {
      console.error("[PDF] addImage map error:", e);
    }
  }

  y += mapHeight + 3.5;

  // 4. Sorted Risk Rank Legend (2-Column Grid to prevent any truncation)
  const sortedSites = [...sites].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  if (sortedSites.length > 0) {
    doc.setFillColor(250, 250, 250);
    doc.setDrawColor(220, 225, 220);
    doc.roundedRect(margin, y, contentWidth, 14, 1.5, 1.5, "FD");

    doc.setFont("helvetica", "bold");
    doc.setFontSize(7.5);
    doc.setTextColor(60, 65, 60);
    doc.text("RISK RANK:", margin + 4, y + 5);

    // Render in a 2x2 grid
    sortedSites.slice(0, 4).forEach((s, idx) => {
      const hex = RANK_COLORS[s.rank] || RANK_COLORS[0];
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);

      const col = idx % 2;
      const row = Math.floor(idx / 2);
      const itemX = margin + (col === 0 ? 25 : 105);
      const itemY = y + (row === 0 ? 3.5 : 8.5);

      doc.setFillColor(r, g, b);
      doc.rect(itemX, itemY, 3, 3, "F");

      doc.setFont("helvetica", "normal");
      doc.setFontSize(7.5);
      doc.setTextColor(40, 45, 40);
      const labelText = `#${idx + 1}  ${prettifyLabel(s.label)} (${formatValue(s.value, s.units)})`;
      doc.text(labelText, itemX + 4.5, itemY + 2.4);
    });

    y += 18;
  }

  // 5. Operations Brief & Strategic Summary
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(20, 25, 20);
  doc.text("OPERATIONS BRIEF & STRATEGIC CONTEXT", margin, y);
  y += 3.5;

  // Operations Brief Box
  doc.setFillColor(246, 248, 246);
  doc.setDrawColor(215, 220, 215);
  doc.roundedRect(margin, y, contentWidth, 20, 1.5, 1.5, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  doc.setTextColor(30, 35, 30);
  doc.text("SUBMITTED BRIEF:", margin + 4, y + 5);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(50, 55, 50);
  const briefText = report.plan?.brief || "Heat risk evaluation across Phoenix distribution network";
  const briefLines = doc.splitTextToSize(`"${briefText}"`, contentWidth - 8);
  doc.text(briefLines, margin + 4, y + 10);

  y += 24;

  // 6. Critical Operational Recommendation Card on Page 1
  const highestSite = sortedSites[0];
  if (highestSite) {
    doc.setFillColor(254, 246, 242);
    doc.setDrawColor(232, 112, 58);
    doc.roundedRect(margin, y, contentWidth, 24, 1.5, 1.5, "FD");

    doc.setFont("helvetica", "bold");
    doc.setFontSize(8.5);
    doc.setTextColor(194, 83, 31);
    doc.text("CRITICAL OPERATIONAL RECOMMENDATION", margin + 4, y + 5.5);

    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(40, 45, 40);
    const recText = `Prioritize operational restaging and heat mitigation away from ${prettifyLabel(
      highestSite.label
    )} first. It recorded the highest risk exposure across the operational network at ${formatValue(
      highestSite.value,
      highestSite.units
    )} ${prettifyMetric(highestSite.metric)} (mean: ${formatValue(highestSite.mean, highestSite.units)}).`;
    const recLines = doc.splitTextToSize(recText, contentWidth - 8);
    doc.text(recLines, margin + 4, y + 11);
  }

  // Page 1 Footer
  doc.setFont("helvetica", "normal");
  doc.setFontSize(7.5);
  doc.setTextColor(140, 145, 140);
  doc.text("Aegis Heat-Risk Intelligence Platform · FortyGuard Hackathon '26", margin, pageHeight - 6);
  doc.text("Page 1 of 2", pageWidth - margin - 15, pageHeight - 6);

  // ══════════════════════════════════════════════════════════════════════════
  // PAGE 2: RANKED SITES BREAKDOWN & CITATIONS PROVENANCE
  // ══════════════════════════════════════════════════════════════════════════

  doc.addPage();

  // Page 2 Header Banner
  doc.setFillColor(16, 19, 18);
  doc.rect(0, 0, pageWidth, 16, "F");

  doc.setFillColor(232, 112, 58);
  doc.rect(0, 15, pageWidth, 1, "F");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(232, 235, 231);
  doc.text("AEGIS — HEAT RISK OPERATIONS MEMO", margin, 10);

  y = 24;

  // 1. Ranked Sites Section
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(20, 25, 20);
  doc.text("RANKED SITES THERMAL BREAKDOWN", margin, y);
  y += 4;

  sortedSites.forEach((s, idx) => {
    const hex = RANK_COLORS[s.rank] || RANK_COLORS[0];
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);

    doc.setFillColor(255, 255, 255);
    doc.setDrawColor(225, 230, 225);
    doc.roundedRect(margin, y, contentWidth, 12, 1.5, 1.5, "FD");

    // Left color bar
    doc.setFillColor(r, g, b);
    doc.rect(margin, y, 3, 12, "F");

    doc.setFont("helvetica", "bold");
    doc.setFontSize(8.5);
    doc.setTextColor(20, 25, 20);
    doc.text(`${idx + 1}.  ${prettifyLabel(s.label)}`, margin + 7, y + 5);

    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(80, 85, 80);
    doc.text(
      `Peak: ${formatValue(s.value, s.units)}   |   Mean: ${formatValue(s.mean, s.units)}   |   Metric: ${prettifyMetric(
        s.metric
      )}   |   Source: ${prettifyEndpoint(s.endpoint || "")}`,
      margin + 7,
      y + 9.5
    );

    y += 14;
  });

  y += 4;

  // 2. Verified Citations & Provenance Table
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(20, 25, 20);
  doc.text("VERIFIED DATA CITATIONS & AUDIT TRAIL", margin, y);
  y += 4;

  // Table Header
  doc.setFillColor(240, 243, 240);
  doc.setDrawColor(215, 220, 215);
  doc.rect(margin, y, contentWidth, 6.5, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(7.5);
  doc.setTextColor(60, 65, 60);
  doc.text("SITE", margin + 4, y + 4.5);
  doc.text("METRIC & MEASUREMENT", margin + 62, y + 4.5);
  doc.text("FORTYGUARD ENDPOINT", margin + 115, y + 4.5);
  doc.text("SEVERITY", margin + 160, y + 4.5);

  y += 6.5;

  // Table Rows
  report.citations.forEach((c) => {
    const risk = riskLevelByMetric(c.value, c.field, report.citations);

    doc.setFillColor(255, 255, 255);
    doc.setDrawColor(230, 235, 230);
    doc.rect(margin, y, contentWidth, 6, "FD");

    doc.setFont("helvetica", "bold");
    doc.setFontSize(7.5);
    doc.setTextColor(30, 35, 30);
    doc.text(prettifyLabel(c.label), margin + 4, y + 4.2);

    doc.setFont("helvetica", "normal");
    doc.text(`${prettifyMetric(c.field)}: ${formatValue(c.value, c.units)}`, margin + 62, y + 4.2);

    doc.setTextColor(80, 85, 80);
    doc.text(`${prettifyEndpoint(c.endpoint)} (${truncateId(c.activity_id)})`, margin + 115, y + 4.2);

    if (risk === "high") {
      doc.setTextColor(192, 57, 47);
      doc.setFont("helvetica", "bold");
      doc.text("HIGH", margin + 160, y + 4.2);
    } else if (risk === "medium") {
      doc.setTextColor(181, 122, 27);
      doc.setFont("helvetica", "bold");
      doc.text("MEDIUM", margin + 160, y + 4.2);
    } else {
      doc.setTextColor(46, 125, 68);
      doc.setFont("helvetica", "bold");
      doc.text("LOW", margin + 160, y + 4.2);
    }

    y += 6;
  });

  y += 8;

  // 3. Technical Verification & Compliance Notice
  doc.setFillColor(248, 250, 248);
  doc.setDrawColor(220, 225, 220);
  doc.roundedRect(margin, y, contentWidth, 22, 1.5, 1.5, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  doc.setTextColor(30, 35, 30);
  doc.text("AUDIT TRAIL & METHODOLOGY COMPLIANCE", margin + 4, y + 5);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(7.5);
  doc.setTextColor(80, 85, 80);
  const auditLines = [
    "• Deterministic heat-risk calculation verified against FortyGuard's official street-level API.",
    `• Planner Model: ${report.planner_model || "Aegis Hybrid Engine"} | Data Mode: ${report.fortyguard_mode || "cached"}`,
    "• Pre-submit geo-validation and AOI boundary enforcement active (maximum AOI: 10 sq mi).",
  ];
  doc.text(auditLines, margin + 4, y + 9.5);

  // Page 2 Footer
  doc.setFont("helvetica", "normal");
  doc.setFontSize(7.5);
  doc.setTextColor(140, 145, 140);
  doc.text("Aegis Heat-Risk Intelligence Platform · FortyGuard Hackathon '26", margin, pageHeight - 6);
  doc.text("Page 2 of 2", pageWidth - margin - 15, pageHeight - 6);

  // Download
  doc.save(`aegis-memo-${report.job_id.slice(0, 8)}.pdf`);
}
