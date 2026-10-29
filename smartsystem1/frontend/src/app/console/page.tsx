"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import {
  Category,
  IssueListItem,
  IssueStatus,
  TriageItem,
  consoleApi,
} from "@/lib/console";
import { useAuth } from "@/lib/auth";

const STATUSES: (IssueStatus | "")[] = [
  "",
  "open",
  "acknowledged",
  "assigned",
  "in_progress",
  "resolved",
  "closed",
];

export default function ConsolePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [queue, setQueue] = useState<TriageItem[]>([]);
  const [issues, setIssues] = useState<IssueListItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [statusFilter, setStatusFilter] = useState<IssueStatus | "">("");
  const [picks, setPicks] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const isStaff = user?.role === "official" || user?.role === "admin";

  const loadIssues = useCallback(async () => {
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    setIssues((await consoleApi.listIssues(qs)).items);
  }, [statusFilter]);

  const loadAll = useCallback(async () => {
    // Load each independently so one failing call can't blank the others.
    await Promise.all([
      consoleApi.triageQueue().then(setQueue).catch(() => {}),
      consoleApi.categories().then(setCategories).catch(() => {}),
      loadIssues(),
    ]);
  }, [loadIssues]);

  useEffect(() => {
    if (!loading && !isStaff) router.replace("/login");
  }, [loading, isStaff, router]);

  useEffect(() => {
    if (isStaff) loadAll();
  }, [isStaff, loadAll]);

  useEffect(() => {
    if (isStaff) loadIssues();
  }, [isStaff, loadIssues]);

  if (loading) return <p className="p-8 text-neutral-500">Loading…</p>;
  if (!isStaff) return <p className="p-8 text-neutral-500">Staff only. Redirecting…</p>;

  async function createIssue(complaintId: string) {
    const categoryId = picks[complaintId] ?? categories[0]?.id;
    if (!categoryId) return;
    setBusy(complaintId);
    try {
      await consoleApi.createIssue(complaintId, categoryId);
      await loadAll();
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">Console</h1>
      <p className="mb-6 text-sm text-neutral-500">
        Signed in as {user?.full_name} ({user?.role})
      </p>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-medium">
          Triage queue <span className="text-neutral-400">({queue.length})</span>
        </h2>
        <p className="mb-3 text-sm text-neutral-500">
          Complaints not yet turned into a tracked issue. Pick a category and create one.
        </p>
        {queue.length === 0 ? (
          <p className="rounded-md border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-400">
            Nothing waiting. New complaints will appear here.
          </p>
        ) : (
          <div className="divide-y rounded-md border border-neutral-200">
            {queue.map((c) => (
              <div key={c.id} className="flex items-center gap-3 p-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{c.description}</p>
                  <p className="text-xs text-neutral-400">
                    {c.public_code} · ward {c.ward_id ?? "—"} ·{" "}
                    {new Date(c.created_at).toLocaleString()}
                  </p>
                </div>
                <select
                  value={picks[c.id] ?? ""}
                  onChange={(e) =>
                    setPicks((p) => ({ ...p, [c.id]: Number(e.target.value) }))
                  }
                  className="rounded-md border border-neutral-300 px-2 py-1.5 text-sm"
                >
                  <option value="">Category…</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name}
                    </option>
                  ))}
                </select>
                <button
                  disabled={busy === c.id || !(picks[c.id] ?? categories[0]?.id)}
                  onClick={() => createIssue(c.id)}
                  className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                >
                  {busy === c.id ? "Creating…" : "Create issue"}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-medium">Issues</h2>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as IssueStatus | "")}
            className="rounded-md border border-neutral-300 px-2 py-1.5 text-sm"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s === "" ? "All statuses" : s}
              </option>
            ))}
          </select>
        </div>
        {issues.length === 0 ? (
          <p className="rounded-md border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-400">
            No issues yet.
          </p>
        ) : (
          <div className="divide-y rounded-md border border-neutral-200">
            {issues.map((i) => (
              <Link
                key={i.id}
                href={`/console/${i.id}`}
                className="flex items-center gap-3 p-3 hover:bg-neutral-50"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{i.title}</p>
                  <p className="text-xs text-neutral-400">
                    {i.public_code} · {i.complaint_count} report(s) · ward {i.ward_id}
                    {i.assigned_to_name ? ` · ${i.assigned_to_name}` : ""}
                  </p>
                </div>
                {i.sla_breached && (
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">
                    SLA breached
                  </span>
                )}
                <StatusBadge status={i.status} />
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
