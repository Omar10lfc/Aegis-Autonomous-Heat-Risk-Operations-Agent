"use client";

import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  prettifyLabel,
  prettifyMetric,
  formatValue,
  prettifyEndpoint,
  truncateId,
} from "../lib/format";

export interface MapSite {
  label: string;
  rank: number;
  value: number | null;
  metric: string | null;
  ring: number[][]; // [[lon, lat], ...]
  endpoint: string | null;
  activity_id: string | null;
  mean: number | null;
  units: string | null;
}

// Rank-based color palette (hotter = more saturated warm)
const RANK_COLORS = ["#e8703a", "#f2a25c", "#d8cf4a", "#7a8f6a"];

// In-memory OSM raster style: no external style fetch, cannot hang.
const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#141b19" } },
    { id: "osm", type: "raster", source: "osm" },
  ],
};

export default function SiteMap({ sites }: { sites: MapSite[] }) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const drawnSites = useRef<string>("");
  const tryDrawRef = useRef<() => void>(() => {});
  const resizeHandlerRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState("loading");
  const [errMsg, setErrMsg] = useState<string | null>(null);

  // ── Map initialization ──
  useEffect(() => {
    if (!container.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: container.current,
      style: OSM_STYLE,
      center: [-112.1, 33.45],
      zoom: 9.5,
      attributionControl: false,
      preserveDrawingBuffer: true,
    } as unknown as maplibregl.MapOptions);
    mapRef.current = map;

    map.on("load", () => {
      setStatus("ready");
      setErrMsg(null);
      tryDrawRef.current();
    });
    map.on("styledata", () => tryDrawRef.current());
    map.on("error", (e) => {
      const err = String(
        e.error instanceof Error
          ? e.error.message
          : JSON.stringify(e.error ?? "")
      );
      console.error("[SiteMap] error event", err);
      setErrMsg(err);
    });

    registerPopups(map);

    const onResize = () => {
      mapRef.current?.resize();
    };
    resizeHandlerRef.current = onResize;
    window.addEventListener("resize", onResize);

    return () => {
      map.remove();
      mapRef.current = null;
      drawnSites.current = "";
      if (resizeHandlerRef.current) {
        window.removeEventListener("resize", resizeHandlerRef.current);
      }
    };
  }, []);

  // ── Sites drawing ──
  useEffect(() => {
    const map = mapRef.current;
    if (!map || sites.length === 0) {
      tryDrawRef.current = () => {};
      return;
    }
    const key = sites.map((s) => s.label).join(",");
    if (key === drawnSites.current) return;

    tryDrawRef.current = () => {
      if (!map.isStyleLoaded()) return;
      if (key === drawnSites.current) return;
      try {
        drawSites(map, sites);
        drawnSites.current = key;
        setErrMsg(null);
      } catch (err) {
        console.error("[SiteMap] drawSites failed", err);
        setErrMsg(String(err));
      }
    };
    tryDrawRef.current();
  }, [sites]);

  // ── Fallback polling ──
  useEffect(() => {
    const t = setInterval(() => {
      const map = mapRef.current;
      if (!map) return;
      const pending = tryDrawRef.current;
      if (
        pending &&
        sites.length > 0 &&
        keyOf(sites) !== drawnSites.current
      ) {
        pending();
      }
    }, 800);
    return () => clearInterval(t);
  }, [sites]);

  return (
    <>
      <div ref={container} style={{ position: "absolute", inset: 0 }} />

      {/* Map legend in the corner */}
      {sites.length > 0 && (
        <div className="map-legend">
          <div className="map-legend-title">Risk Rank</div>
          {sites
            .slice()
            .sort((a, b) => a.rank - b.rank)
            .map((s) => (
              <div key={s.label} className="map-legend-item">
                <span
                  className="map-legend-swatch"
                  style={{
                    background: RANK_COLORS[s.rank] ?? RANK_COLORS[0],
                  }}
                />
                <span className="map-legend-label">
                  {prettifyLabel(s.label)}
                </span>
              </div>
            ))}
        </div>
      )}

      {/* Loading indicator */}
      {status !== "ready" && (
        <div
          style={{
            position: "absolute",
            top: 8,
            left: 8,
            zIndex: 10,
            padding: "6px 10px",
            borderRadius: 6,
            background: "rgba(10,12,10,0.85)",
            color: errMsg ? "#e5544b" : "#9aa39a",
            font: "12px monospace",
            pointerEvents: "none",
          }}
        >
          {errMsg ? `Map error — ${errMsg}` : "Loading map…"}
        </div>
      )}
    </>
  );
}

function keyOf(sites: readonly { label: string }[]): string {
  return sites.map((s) => s.label).join(",");
}

function drawSites(map: maplibregl.Map, sites: MapSite[]) {
  const source = map.getSource("sites") as
    | maplibregl.GeoJSONSource
    | undefined;
  const hasFill = map.getLayer("site-fill");
  const features = sites.map((s) => ({
    type: "Feature" as const,
    properties: {
      label: s.label,
      rank: s.rank,
      value: s.value ?? 0,
      metric: s.metric ?? "",
      endpoint: s.endpoint ?? "",
      activity_id: s.activity_id ?? "",
      mean: s.mean ?? null,
      units: s.units ?? "",
    },
    geometry: { type: "Polygon" as const, coordinates: [s.ring] },
  }));
  const fc = { type: "FeatureCollection" as const, features };

  if (!source) {
    map.addSource("sites", { type: "geojson", data: fc });
  } else {
    source.setData(fc);
  }

  if (!hasFill) {
    map.addLayer({
      id: "site-fill",
      type: "fill",
      source: "sites",
      paint: {
        "fill-color": [
          "interpolate",
          ["linear"],
          ["get", "rank"],
          0,
          "#e8703a",
          1,
          "#f2a25c",
          2,
          "#d8cf4a",
          3,
          "#7a8f6a",
        ],
        "fill-opacity": 0.55,
      },
    });
    map.addLayer({
      id: "site-outline",
      type: "line",
      source: "sites",
      paint: { "line-color": "#ffffff", "line-width": 3 },
    });
    map.addLayer({
      id: "site-outline-core",
      type: "line",
      source: "sites",
      paint: { "line-color": "#c2531f", "line-width": 1.5 },
    });
  }

  const bounds = new maplibregl.LngLatBounds();
  sites.forEach((s) =>
    s.ring.forEach(([lon, lat]) => bounds.extend([lon, lat]))
  );
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 70, maxZoom: 12.5, animate: false });
  }
}

const popupBoundMaps = new WeakSet<maplibregl.Map>();

function registerPopups(map: maplibregl.Map) {
  if (popupBoundMaps.has(map)) return;
  popupBoundMaps.add(map);

  let popup: maplibregl.Popup | null = null;
  let lastLabel: string | null = null;

  const showAt = (
    lngLat: maplibregl.LngLat,
    props: {
      label: string;
      value: number;
      metric: string;
      endpoint: string | null;
      activityId: string | null;
      mean: number | null;
      units: string;
    }
  ) => {
    popup?.remove();
    const name = prettifyLabel(props.label);
    const metricName = prettifyMetric(props.metric);
    const rows = [
      `<strong style="font-size:13px">${name}</strong>`,
      `<span style="color:#9aa39a">${metricName}</span> = <strong>${formatValue(props.value, props.units)}</strong>`,
    ];
    if (props.mean !== null && props.mean !== undefined) {
      rows.push(
        `<span style="color:#9aa39a">Mean: ${formatValue(props.mean, props.units)}</span>`
      );
    }
    if (props.endpoint) {
      rows.push(
        `<span style="color:#6b736b;font-size:10px">${prettifyEndpoint(props.endpoint)}${
          props.activityId
            ? ` · <code>${truncateId(props.activityId)}</code>`
            : ""
        }</span>`
      );
    }
    popup = new maplibregl.Popup({ closeButton: false, offset: 10 })
      .setLngLat(lngLat)
      .setHTML(
        `<div style="font:12px/1.5 var(--font-mono,monospace)">${rows.join("<br/>")}</div>`
      )
      .addTo(map);
    lastLabel = props.label;
  };

  map.on("mousemove", (e) => {
    if (!map.getLayer("site-fill")) return;
    const features = map.queryRenderedFeatures(e.point, {
      layers: ["site-fill"],
    }) as maplibregl.MapGeoJSONFeature[];
    const f = features[0];
    const props = (f?.properties ?? {}) as {
      label?: string;
      value?: number;
      metric?: string;
      endpoint?: string;
      activity_id?: string;
      mean?: number;
      units?: string;
    };
    if (props.label !== undefined) {
      map.getCanvas().style.cursor = "pointer";
      if (props.label !== lastLabel) {
        showAt(e.lngLat, {
          label: props.label,
          value: props.value ?? 0,
          metric: props.metric ?? "",
          endpoint: props.endpoint ?? null,
          activityId: props.activity_id ?? null,
          mean: props.mean ?? null,
          units: props.units ?? "",
        });
      } else {
        popup?.setLngLat(e.lngLat);
      }
    } else {
      map.getCanvas().style.cursor = "";
      if (popup) {
        popup.remove();
        popup = null;
        lastLabel = null;
      }
    }
  });

  map.on("mouseout", () => {
    map.getCanvas().style.cursor = "";
    if (popup) {
      popup.remove();
      popup = null;
      lastLabel = null;
    }
  });
}