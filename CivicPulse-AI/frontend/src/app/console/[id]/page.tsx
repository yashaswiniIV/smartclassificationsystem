"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { ApiError } from "@/lib/api";
import {
  IssueDetail,
  IssueMedia,
  IssueStatus,
  NEXT_STATUSES,
  StaffMember,
  TimelineEntry,
  consoleApi,
} from "@/lib/console";
import { useAuth } from "@/lib/auth";

const NOTE_REQUIRED: IssueStatus[] = ["resolved", "rejected"];

export default function IssueDetailPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [issue, setIssue] = useState<IssueDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [media, setMedia] = useState<IssueMedia[]>([]);
  const [assignees, setAssignees] = useState<StaffMember[]>([]);
  const [note, setNote] = useState("");
  const [updateBody, setUpdateBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canAssign = user?.role === "admin" || user?.is_department_head;

  const load = useCallback(async () => {
    const [iss, tl, md] = await Promise.all([
      consoleApi.getIssue(id),
      consoleApi.timeline(id),
      consoleApi.issueMedia(id).catch(() => []),
    ]);
    setIssue(iss);
    setTimeline(tl);
    setMedia(md);
    if (canAssign) setAssignees(await consoleApi.assignees(iss.department_id));
  }, [id, canAssign]);

  useEffect(() => {
    load().catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load"));
  }, [load]);

  async function doTransition(to: IssueStatus) {
    setError(null);
    if (NOTE_REQUIRED.includes(to) && !note.trim()) {
      setError(`A note is required to mark this ${to}.`);
      return;
    }
    setBusy(true);
    try {
      await consoleApi.changeStatus(id, to, note.trim() || undefined);
      setNote("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Transition failed");
    } finally {
      setBusy(false);
    }
  }

  async function doAssign(assigneeId: string) {
    setBusy(true);
    setError(null);
    try {
      await consoleApi.assign(id, assigneeId);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Assign failed");
    } finally {
      setBusy(false);
    }
  }

  async function addUpdate(isInternal: boolean) {
    if (!updateBody.trim()) return;
    setBusy(true);
    try {
      await consoleApi.addUpdate(id, updateBody.trim(), isInternal);
      setUpdateBody("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (!issue) {
    return <p className="p-8 text-neutral-500">{error ?? "Loading…"}</p>;
  }

  const nexts = NEXT_STATUSES[issue.status];

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/console" className="text-sm text-blue-600 hover:underline">
        ← Back to console
      </Link>

      <div className="mt-3 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{issue.title}</h1>
          <p className="text-sm text-neutral-400">
            {issue.public_code} · {issue.complaint_count} report(s) · ward {issue.ward_id}
          </p>
        </div>
        <StatusBadge status={issue.status} />
      </div>

      {issue.sla_breached && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          SLA breached — due {new Date(issue.sla_due_at).toLocaleString()}
        </p>
      )}
      {issue.resolution_note && (
        <p className="mt-3 rounded-md bg-green-50 px-3 py-2 text-sm text-green-800">
          Resolution: {issue.resolution_note}
        </p>
      )}

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      {/* Actions */}
      <section className="mt-6 rounded-md border border-neutral-200 p-4">
        <h2 className="mb-2 text-sm font-medium">Actions</h2>
        {nexts.length === 0 ? (
          <p className="text-sm text-neutral-400">This issue is closed — no further actions.</p>
        ) : (
          <>
            {nexts.some((s) => NOTE_REQUIRED.includes(s)) && (
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Note (required to resolve or reject)"
                rows={2}
                className="mb-2 w-full rounded-md border border-neutral-300 px-3 py-2 text-sm"
              />
            )}
            <div className="flex flex-wrap gap-2">
              {nexts.map((s) =>
                s === "assigned" ? null : (
                  <button
                    key={s}
                    disabled={busy}
                    onClick={() => doTransition(s)}
                    className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50"
                  >
                    Mark {s.replace("_", " ")}
                  </button>
                ),
              )}
            </div>
          </>
        )}

        {canAssign && (issue.status === "acknowledged" || issue.status === "reopened") && (
          <div className="mt-3 border-t pt-3">
            <label className="mb-1 block text-sm font-medium">Assign to official</label>
            <select
              defaultValue=""
              disabled={busy}
              onChange={(e) => e.target.value && doAssign(e.target.value)}
              className="rounded-md border border-neutral-300 px-2 py-1.5 text-sm"
            >
              <option value="">Choose official…</option>
              {assignees.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.full_name}
                </option>
              ))}
            </select>
          </div>
        )}
      </section>

      {/* Photos + AI detection */}
      {media.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-sm font-medium">Photos &amp; AI detection</h2>
          <div className="flex flex-wrap gap-3">
            {media.map((m) => (
              <div key={m.id} className="w-40">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={m.url}
                  alt="complaint"
                  className="h-28 w-40 rounded-md border border-neutral-200 object-cover"
                />
                <div className="mt-1 flex flex-wrap gap-1">
                  {m.cv_result?.labels?.map((l, i) => (
                    <span
                      key={i}
                      className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-800"
                    >
                      {l.label} {Math.round(l.conf * 100)}%
                    </span>
                  ))}
                  {m.moderation === "flagged" && (
                    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700">
                      flagged
                    </span>
                  )}
                  {m.cv_status === "pending" && (
                    <span className="text-xs text-neutral-400">analyzing…</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Add update */}
      <section className="mt-6">
        <h2 className="mb-2 text-sm font-medium">Add a progress note</h2>
        <textarea
          value={updateBody}
          onChange={(e) => setUpdateBody(e.target.value)}
          placeholder="What's the latest on this issue?"
          rows={2}
          className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm"
        />
        <div className="mt-2 flex gap-2">
          <button
            disabled={busy || !updateBody.trim()}
            onClick={() => addUpdate(false)}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Post (public)
          </button>
          <button
            disabled={busy || !updateBody.trim()}
            onClick={() => addUpdate(true)}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-100 disabled:opacity-50"
          >
            Post (internal)
          </button>
        </div>
      </section>

      {/* Timeline */}
      <section className="mt-8">
        <h2 className="mb-3 text-sm font-medium">Timeline</h2>
        <ol className="relative border-l border-neutral-200 pl-4">
          {timeline.map((e, idx) => (
            <li key={idx} className="mb-4">
              <div className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-neutral-300" />
              <p className="text-sm">
                {e.kind === "status" ? (
                  <span>
                    Status → <span className="font-medium">{e.to_status}</span>
                    {e.text ? `: ${e.text}` : ""}
                  </span>
                ) : (
                  <span>
                    {e.is_internal && (
                      <span className="mr-1 rounded bg-neutral-200 px-1 text-xs">internal</span>
                    )}
                    {e.text}
                  </span>
                )}
              </p>
              <p className="text-xs text-neutral-400">
                {new Date(e.created_at).toLocaleString()}
              </p>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
