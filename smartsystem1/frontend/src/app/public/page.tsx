"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PublicStats, analyticsApi } from "@/lib/analytics";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-neutral-200 p-4 text-center">
      <div className="text-3xl font-semibold">{value}</div>
      <div className="mt-1 text-sm text-neutral-500">{label}</div>
    </div>
  );
}

export default function PublicDashboard() {
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    analyticsApi.publicStats().then(setStats).catch(() => setError(true));
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-2xl font-semibold">Bengaluru — civic transparency</h1>
      <p className="mb-8 mt-1 text-sm text-neutral-500">
        Live, anonymized view of civic issues across the city. No login required.
      </p>

      {error && <p className="text-sm text-red-600">Couldn&apos;t load stats right now.</p>}

      {stats && (
        <>
          <div className="mb-10 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Total issues" value={stats.total_issues.toLocaleString()} />
            <Stat label="Open" value={stats.open_issues.toLocaleString()} />
            <Stat label="Resolved" value={stats.resolved_issues.toLocaleString()} />
            <Stat label="Resolved rate" value={`${stats.resolved_pct}%`} />
          </div>

          <h2 className="mb-3 text-lg font-medium">Most reported categories</h2>
          <div className="h-80 w-full rounded-lg border border-neutral-200 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={stats.top_categories}
                layout="vertical"
                margin={{ top: 8, right: 24, bottom: 8, left: 40 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={140}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip />
                <Bar dataKey="count" name="Issues" fill="#534AB7" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      <p className="mt-10 text-sm text-neutral-500">
        Want to report a problem?{" "}
        <Link href="/report" className="underline">
          File a complaint
        </Link>
      </p>
    </main>
  );
}
