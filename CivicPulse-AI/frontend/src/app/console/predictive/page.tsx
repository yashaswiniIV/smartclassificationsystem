"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Category,
  ForecastOut,
  Hotspot,
  WardRisk,
  analyticsApi,
} from "@/lib/analytics";
import { useAuth } from "@/lib/auth";

export default function PredictivePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const isStaff = user?.role === "official" || user?.role === "admin";
  const isAdmin = user?.role === "admin";

  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [catId, setCatId] = useState<number | null>(null);
  const [forecast, setForecast] = useState<ForecastOut | null>(null);
  const [risk, setRisk] = useState<WardRisk[]>([]);
  const [cause, setCause] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!loading && !isStaff) router.replace("/login");
  }, [loading, isStaff, router]);

  const load = useCallback(async () => {
    await Promise.all([
      analyticsApi.hotspots().then(setHotspots).catch(() => {}),
      analyticsApi.categories().then((c) => {
        setCats(c);
        if (c.length) setCatId((prev) => prev ?? c[0].id);
      }).catch(() => {}),
      isAdmin ? analyticsApi.wardRisk().then(setRisk).catch(() => {}) : Promise.resolve(),
    ]);
  }, [isAdmin]);

  useEffect(() => {
    if (isStaff) load();
  }, [isStaff, load]);

  useEffect(() => {
    if (catId != null) analyticsApi.forecast(catId).then(setForecast).catch(() => setForecast(null));
  }, [catId]);

  if (loading) return <p className="p-8 text-neutral-500">Loading…</p>;
  if (!isStaff) return <p className="p-8 text-neutral-500">Staff only. Redirecting…</p>;

  // Build a single chart series: history counts, then forecast mean + CI band.
  const chartData = forecast
    ? [
        ...forecast.history.map((h) => ({ week: h.week, actual: h.count })),
        ...forecast.forecast.map((f) => ({
          week: f.week,
          mean: f.mean,
          band: [f.lower, f.upper] as [number, number],
        })),
      ]
    : [];

  async function loadCause(wardId: number) {
    const rc = await analyticsApi.rootCause(wardId);
    setCause((c) => ({ ...c, [wardId]: rc.hypothesis }));
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Predictive governance</h1>
        <Link href="/console/analytics" className="text-sm text-blue-600 hover:underline">
          ← Analytics
        </Link>
      </div>

      <section className="mb-10">
        <h2 className="mb-1 text-lg font-medium">Emerging hotspots</h2>
        <p className="mb-3 text-sm text-neutral-500">
          Ward × category where the last 2 weeks run ≥2× the prior 8-week baseline — caught
          before the totals peak.
        </p>
        {hotspots.length === 0 ? (
          <p className="rounded-md border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-400">
            No emerging hotspots right now.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {hotspots.slice(0, 6).map((h) => (
              <div
                key={`${h.ward_id}-${h.category_id}`}
                className="rounded-md border border-neutral-200 p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{h.category_name}</span>
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                    {h.ratio}× rising
                  </span>
                </div>
                <p className="mt-1 text-sm text-neutral-500">{h.ward_name}</p>
                <p className="text-xs text-neutral-400">
                  {h.recent_per_week}/wk now vs {h.baseline_per_week}/wk baseline
                </p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="mb-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-medium">4-week forecast</h2>
          <select
            value={catId ?? ""}
            onChange={(e) => setCatId(Number(e.target.value))}
            className="rounded-md border border-neutral-300 px-2 py-1.5 text-sm"
          >
            {cats.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        {forecast?.status === "insufficient_history" ? (
          <p className="rounded-md border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-400">
            Not enough history to forecast this category yet.
          </p>
        ) : (
          <div className="h-72 w-full rounded-lg border border-neutral-200 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="week" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Area
                  dataKey="band"
                  stroke="none"
                  fill="#534AB7"
                  fillOpacity={0.15}
                  name="80% CI"
                />
                <Line dataKey="actual" stroke="#185FA5" dot={false} name="Actual" />
                <Line dataKey="mean" stroke="#534AB7" strokeDasharray="5 4" dot name="Forecast" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        {forecast?.model && (
          <p className="mt-2 text-xs text-neutral-400">Model: {forecast.model.toUpperCase()}</p>
        )}
      </section>

      {isAdmin && (
        <section>
          <h2 className="mb-3 text-lg font-medium">Ward risk ranking</h2>
          <div className="divide-y rounded-lg border border-neutral-200">
            {risk.map((w) => (
              <div key={w.ward_id} className="p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">{w.ward_name}</span>
                    <span className="ml-2 text-xs text-neutral-400">
                      open {w.open_count} · breach{" "}
                      {Math.round(w.factors.sla_breach_rate * 100)}% · trend{" "}
                      {Math.round(w.factors.rising_trend * 100)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-semibold">{w.risk_score}</span>
                    <button
                      onClick={() => loadCause(w.ward_id)}
                      className="rounded-md border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100"
                    >
                      Why?
                    </button>
                  </div>
                </div>
                {cause[w.ward_id] && (
                  <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
                    {cause[w.ward_id]}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
