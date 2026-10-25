"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { HeatCell } from "@/lib/analytics";

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
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

function toGeoJSON(cells: HeatCell[]) {
  return {
    type: "FeatureCollection" as const,
    features: cells.map((c) => ({
      type: "Feature" as const,
      properties: { weight: c.weight },
      geometry: { type: "Point" as const, coordinates: [c.lng, c.lat] },
    })),
  };
}

export function HeatmapMap({ cells }: { cells: HeatCell[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OSM_STYLE,
      center: [77.5946, 12.9716],
      zoom: 10.5,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      map.addSource("heat", { type: "geojson", data: toGeoJSON([]) });
      map.addLayer({
        id: "heat",
        type: "heatmap",
        source: "heat",
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "weight"], 0, 0, 20, 1],
          "heatmap-radius": 22,
          "heatmap-opacity": 0.7,
        },
      });
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Push new cells into the source whenever they change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const src = map.getSource("heat") as maplibregl.GeoJSONSource | undefined;
      if (src) src.setData(toGeoJSON(cells));
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [cells]);

  return (
    <div
      ref={containerRef}
      className="h-96 w-full overflow-hidden rounded-lg border border-neutral-300"
    />
  );
}
