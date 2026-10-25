"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { HeatmapMap } from "@/components/HeatmapMap";
import {
  DepartmentRow,
  HeatCell,
  TrendPoint,
  analyticsApi,
} from "@/lib/analytics";
import { useAuth } from "@/lib/auth";

export default function AnalyticsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const isStaff = user?.role === "official" || user?.role === "admin";
  const isAdmin = user?.role === "admin";

  const [cells, setCells] = useState<HeatCell[]>([]);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [depts, setDepts] = useState<DepartmentRow[]>([]);

  const load = useCallback(async () => {
    await Promise.all([
      analyticsApi.heatmap().then(setCells).catch(() => {}),
      analyticsApi.trends(26).then(setTrends).catch(() => {}),
      isAdmin ? analyticsApi.departments().then(setDepts).catch(() => {}) : Promise.resolve(),
    ]);
  }, [isAdmin]);

  useEffect(() => {
    if (!loading && !isStaff) router.replace("/login");
  }, [loading, isStaff, router]);
  useEffect(() => {
    if (isStaff) load();
  }, [isStaff, load]);

  if (loading) return <p className="p-8 text-neutral-500">Loading…</p>;
  if (!isStaff) return <p className="p-8 text-neutral-500">Staff only. Redirecting…</p>;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">City analytics</h1>
        <Link href="/console" className="text-sm text-blue-600 hover:underline">
          ← Console
        </Link>
      </div>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-medium">Complaint heatmap</h2>
        <HeatmapMap cells={cells} />
        <p className="mt-2 text-xs text-neutral-400">
          {cells.length} grid cells (≈400 m) aggregated server-side from complaint locations.
        </p>
      </section>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-medium">New vs resolved issues (weekly)</h2>
        <div className="h-72 w-full rounded-lg border border-neutral-200 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trends} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="week" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="new_issues" name="New" stroke="#D85A30" dot={false} />
              <Line
                type="monotone"
                dataKey="resolved_issues"
                name="Resolved"
                stroke="#1D9E75"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {isAdmin && (
        <section>
          <h2 className="mb-3 text-lg font-medium">Department performance</h2>
          <div className="overflow-x-auto rounded-lg border border-neutral-200">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-left text-neutral-500">
                <tr>
                  <th className="px-3 py-2">Department</th>
                  <th className="px-3 py-2">Open</th>
                  <th className="px-3 py-2">Total</th>
                  <th className="px-3 py-2">Median resolution</th>
                  <th className="px-3 py-2">SLA breach</th>
                  <th className="px-3 py-2">Reopened</th>
                </tr>
              </thead>
              <tbody>
                {depts.map((d) => (
                  <tr key={d.department_id} className="border-t">
                    <td className="px-3 py-2 font-medium">{d.name}</td>
                    <td className="px-3 py-2">{d.open_count}</td>
                    <td className="px-3 py-2">{d.total}</td>
                    <td className="px-3 py-2">
                      {d.median_resolution_hours != null
                        ? `${d.median_resolution_hours} h`
                        : "—"}
                    </td>
                    <td
                      className={`px-3 py-2 ${d.sla_breach_pct > 40 ? "text-red-600" : ""}`}
                    >
                      {d.sla_breach_pct}%
                    </td>
                    <td className="px-3 py-2">{d.reopened_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
