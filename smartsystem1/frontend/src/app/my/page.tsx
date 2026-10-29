"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Complaint = {
  id: string;
  public_code: string;
  description: string;
  processing_status: string;
  ward_id: number | null;
  created_at: string;
  issue_id: string | null;
  issue_status: string | null;
  issue_public_code: string | null;
};

export default function MyComplaintsPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState<Complaint[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    if (user) api.get<Complaint[]>("/complaints/mine").then(setItems).catch(() => setItems([]));
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  async function confirm(issueId: string) {
    setBusy(issueId);
    try {
      await api.post(`/issues/${issueId}/confirm-resolution`);
      load();
    } finally {
      setBusy(null);
    }
  }

  async function reopen(issueId: string) {
    const reason = window.prompt("What's still wrong? (this reopens the issue)");
    if (!reason) return;
    setBusy(issueId);
    try {
      await api.post(`/issues/${issueId}/reopen`, { reason });
      load();
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <p className="p-8 text-neutral-500">Loading…</p>;
  if (!user)
    return (
      <main className="mx-auto mt-16 max-w-md px-4 text-center">
        <p className="mb-4">Please log in to see your complaints.</p>
        <Link href="/login" className="rounded-md bg-neutral-900 px-4 py-2 text-white">
          Log in
        </Link>
      </main>
    );

  return (
    <main className="mx-auto my-10 max-w-2xl px-4">
      <h1 className="mb-6 text-2xl font-semibold">My complaints</h1>
      {items === null ? (
        <p className="text-neutral-500">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-neutral-500">
          No complaints yet.{" "}
          <Link href="/report" className="underline">
            Report one
          </Link>
          .
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((c) => (
            <li key={c.id} className="rounded-lg border border-neutral-200 p-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm">{c.public_code}</span>
                {c.issue_status ? (
                  <StatusBadge status={c.issue_status} />
                ) : (
                  <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs">
                    {c.processing_status}
                  </span>
                )}
              </div>
              <p className="mt-1 text-neutral-700">{c.description}</p>
              <p className="mt-1 text-xs text-neutral-400">
                {new Date(c.created_at).toLocaleString()}
                {c.ward_id ? ` · ward #${c.ward_id}` : ""}
                {c.issue_public_code ? ` · issue ${c.issue_public_code}` : ""}
              </p>

              {/* When the official marks it resolved, the citizen closes the loop. */}
              {c.issue_id && c.issue_status === "resolved" && (
                <div className="mt-3 flex items-center gap-2 rounded-md bg-green-50 px-3 py-2">
                  <span className="text-sm text-green-800">Marked resolved — is it fixed?</span>
                  <button
                    disabled={busy === c.issue_id}
                    onClick={() => confirm(c.issue_id!)}
                    className="ml-auto rounded-md bg-neutral-900 px-3 py-1 text-xs text-white disabled:opacity-50"
                  >
                    Yes, confirm
                  </button>
                  <button
                    disabled={busy === c.issue_id}
                    onClick={() => reopen(c.issue_id!)}
                    className="rounded-md border border-neutral-300 px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50"
                  >
                    No, reopen
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
