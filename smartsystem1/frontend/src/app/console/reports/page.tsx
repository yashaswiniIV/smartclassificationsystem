"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Report, ReportListItem, consoleApi } from "@/lib/console";
import { useAuth } from "@/lib/auth";

export default function ReportsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const isStaff = user?.role === "official" || user?.role === "admin";
  const isAdmin = user?.role === "admin";

  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [open, setOpen] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [slaMsg, setSlaMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !isStaff) router.replace("/login");
  }, [loading, isStaff, router]);

  const load = useCallback(() => {
    if (isStaff) consoleApi.listReports().then(setReports).catch(() => {});
  }, [isStaff]);

  useEffect(() => {
    load();
  }, [load]);

  async function generate() {
    setBusy(true);
    try {
      const r = await consoleApi.generateReport();
      setOpen(r);
      load();
    } finally {
      setBusy(false);
    }
  }

  async function runSla() {
    setBusy(true);
    try {
      const { breached } = await consoleApi.scanSla();
      setSlaMsg(`SLA scan complete — ${breached} issue(s) newly breached.`);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="p-8 text-neutral-500">Loading…</p>;
  if (!isStaff) return <p className="p-8 text-neutral-500">Staff only. Redirecting…</p>;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Reports</h1>
        <Link href="/console" className="text-sm text-blue-600 hover:underline">
          ← Console
        </Link>
      </div>

      {isAdmin && (
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <button
            disabled={busy}
            onClick={generate}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {busy ? "Working…" : "Generate weekly report"}
          </button>
          <button
            disabled={busy}
            onClick={runSla}
            className="rounded-md border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 disabled:opacity-50"
          >
            Run SLA breach scan
          </button>
          {slaMsg && <span className="text-sm text-neutral-500">{slaMsg}</span>}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-[260px_1fr]">
        <ul className="flex flex-col gap-2">
          {reports.length === 0 && (
            <li className="text-sm text-neutral-400">No reports yet.</li>
          )}
          {reports.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => consoleApi.getReport(r.id).then(setOpen)}
                className={`w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-neutral-50 ${
                  open?.id === r.id ? "border-neutral-900" : "border-neutral-200"
                }`}
              >
                <div className="font-medium">
                  {r.period_start} → {r.period_end}
                </div>
                <div className="text-xs text-neutral-400">
                  {new Date(r.created_at).toLocaleString()}
                </div>
              </button>
            </li>
          ))}
        </ul>

        <div className="rounded-lg border border-neutral-200 p-4">
          {open ? (
            <article className="whitespace-pre-wrap text-sm leading-7">
              {open.content_md}
            </article>
          ) : (
            <p className="text-sm text-neutral-400">Select or generate a report to view it.</p>
          )}
        </div>
      </div>
    </main>
  );
}
