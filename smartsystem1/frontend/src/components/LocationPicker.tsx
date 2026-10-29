"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";

export type LngLat = { lng: number; lat: number };

const BENGALURU: LngLat = { lng: 77.5946, lat: 12.9716 };

// Free OSM raster tiles — no API key, no billing (see ADR-12).
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

export function LocationPicker({
  value,
  onChange,
}: {
  value: LngLat | null;
  onChange: (v: LngLat) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OSM_STYLE,
      center: [BENGALURU.lng, BENGALURU.lat],
      zoom: 11,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("click", (e) => onChange({ lng: e.lngLat.lng, lat: e.lngLat.lat }));
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // onChange is stable enough for this demo; intentionally run once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reflect the selected point as a draggable marker.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !value) return;
    if (!markerRef.current) {
      const marker = new maplibregl.Marker({ draggable: true, color: "#D85A30" });
      marker.on("dragend", () => {
        const { lng, lat } = marker.getLngLat();
        onChange({ lng, lat });
      });
      markerRef.current = marker;
    }
    markerRef.current.setLngLat([value.lng, value.lat]).addTo(map);
  }, [value, onChange]);

  function useMyLocation() {
    navigator.geolocation?.getCurrentPosition((pos) => {
      const here = { lng: pos.coords.longitude, lat: pos.coords.latitude };
      onChange(here);
      mapRef.current?.flyTo({ center: [here.lng, here.lat], zoom: 16 });
    });
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={containerRef}
        className="h-72 w-full overflow-hidden rounded-lg border border-neutral-300"
      />
      <div className="flex items-center justify-between text-sm text-neutral-500">
        <button
          type="button"
          onClick={useMyLocation}
          className="rounded-md border border-neutral-300 px-3 py-1 hover:bg-neutral-100"
        >
          Use my location
        </button>
        <span>
          {value
            ? `Pinned: ${value.lat.toFixed(5)}, ${value.lng.toFixed(5)}`
            : "Tap the map to drop a pin"}
        </span>
      </div>
    </div>
  );
}
