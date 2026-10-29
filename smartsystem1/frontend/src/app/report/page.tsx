"use client";

import Link from "next/link";
import { useState } from "react";

import { LocationPicker, type LngLat } from "@/components/LocationPicker";
import { StatusBadge } from "@/components/StatusBadge";
import { ApiError, api, uploadToStorage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type ComplaintOut = { id: string; public_code: string; ward_id: number | null };
type Presign = { upload_url: string; object_key: string };
type SimilarIssue = {
  issue_id: string;
  public_code: string;
  title: string;
  status: string;
  complaint_count: number;
  upvote_count: number;
  similarity: number;
  distance_m: number;
};

export default function ReportPage() {
  const { user, loading } = useAuth();
  const [description, setDescription] = useState("");
  const [address, setAddress] = useState("");
  const [location, setLocation] = useState<LngLat | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComplaintOut | null>(null);
  const [upvoted, setUpvoted] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<SimilarIssue[] | null>(null);

  if (loading) return <p className="p-8 text-neutral-500">Loading…</p>;
  if (!user)
    return (
      <main className="mx-auto mt-16 max-w-md px-4 text-center">
        <p className="mb-4">Please log in to report a problem.</p>
        <Link href="/login" className="rounded-md bg-neutral-900 px-4 py-2 text-white">
          Log in
        </Link>
      </main>
    );

  // Step 1: before filing, check for an existing nearby issue (the intercept).
  async function onCheck(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!location) {
      setError("Drop a pin on the map first.");
      return;
    }
    setBusy(true);
    try {
      const { candidates: found } = await api.post<{ candidates: SimilarIssue[] }>(
        "/complaints/similar-check",
        { description, location: { type: "Point", coordinates: [location.lng, location.lat] } },
      );
      if (found.length > 0) {
        setCandidates(found); // show the intercept, don't file yet
      } else {
        await fileComplaint(false); // nothing similar — file straight away
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  // Step 2a: citizen says "yes, that's my problem too" → upvote instead of duplicating.
  async function onUpvote(issue: SimilarIssue) {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/issues/${issue.issue_id}/upvote`);
      setUpvoted(issue.public_code);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upvote");
    } finally {
      setBusy(false);
    }
  }

  // Step 2b: "none of these" → file a new complaint (declined the intercept).
  async function fileComplaint(declined: boolean) {
    if (!location) return;
    setBusy(true);
    try {
      const complaint = await api.post<ComplaintOut>("/complaints", {
        description,
        address_text: address || null,
        location: { type: "Point", coordinates: [location.lng, location.lat] },
        declined_intercept: declined,
      });
      if (file) {
        const ps = await api.post<Presign>(`/complaints/${complaint.id}/media/presign`, {
          mime: file.type,
          bytes: file.size,
        });
        await uploadToStorage(ps.upload_url, file);
        await api.post(`/complaints/${complaint.id}/media/confirm`, {
          object_key: ps.object_key,
          mime: file.type,
        });
      }
      setResult(complaint);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setResult(null);
    setUpvoted(null);
    setCandidates(null);
    setDescription("");
    setAddress("");
    setLocation(null);
    setFile(null);
  }

  if (upvoted)
    return (
      <main className="mx-auto mt-16 max-w-md px-4 text-center">
        <h1 className="mb-2 text-2xl font-semibold">You&apos;re following it ✓</h1>
        <p className="text-neutral-600">
          Thanks — instead of a duplicate, we added your voice to{" "}
          <span className="font-mono">{upvoted}</span>. You&apos;ll get updates as it progresses.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button onClick={reset} className="rounded-md border px-4 py-2 hover:bg-neutral-100">
            Report something else
          </button>
          <Link href="/my" className="rounded-md bg-neutral-900 px-4 py-2 text-white">
            My complaints
          </Link>
        </div>
      </main>
    );

  if (result)
    return (
      <main className="mx-auto mt-16 max-w-md px-4 text-center">
        <h1 className="mb-2 text-2xl font-semibold">Reported ✓</h1>
        <p className="text-neutral-600">
          Your reference is <span className="font-mono">{result.public_code}</span>.
          {result.ward_id
            ? " We've located it in your ward and our AI will categorize it shortly."
            : " (This location is outside the pilot city.)"}
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button onClick={reset} className="rounded-md border px-4 py-2 hover:bg-neutral-100">
            Report another
          </button>
          <Link href="/my" className="rounded-md bg-neutral-900 px-4 py-2 text-white">
            Track my complaints
          </Link>
        </div>
      </main>
    );

  // Intercept panel: nearby open issues that look like the same problem.
  if (candidates && candidates.length > 0)
    return (
      <main className="mx-auto my-10 max-w-2xl px-4">
        <h1 className="mb-2 text-2xl font-semibold">Is this already reported?</h1>
        <p className="mb-5 text-sm text-neutral-500">
          We found {candidates.length} open issue{candidates.length > 1 ? "s" : ""} near you that
          look like the same problem. Adding your voice helps more than a duplicate.
        </p>
        <div className="flex flex-col gap-3">
          {candidates.map((c) => (
            <div key={c.issue_id} className="rounded-md border border-neutral-200 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{c.title}</p>
                  <p className="mt-0.5 text-xs text-neutral-400">
                    {c.public_code} · {Math.round(c.distance_m)} m away · {c.complaint_count}{" "}
                    report(s) · {Math.round(c.similarity * 100)}% match
                  </p>
                </div>
                <StatusBadge status={c.status} />
              </div>
              <button
                disabled={busy}
                onClick={() => onUpvote(c)}
                className="mt-3 rounded-md bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                Yes, this is it — notify me too (+1)
              </button>
            </div>
          ))}
        </div>
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
        <div className="mt-6 flex items-center gap-3">
          <button
            disabled={busy}
            onClick={() => fileComplaint(true)}
            className="rounded-md border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 disabled:opacity-50"
          >
            None of these — file a new report
          </button>
          <button
            disabled={busy}
            onClick={() => setCandidates(null)}
            className="text-sm text-neutral-500 hover:underline"
          >
            Back to edit
          </button>
        </div>
      </main>
    );

  return (
    <main className="mx-auto my-10 max-w-2xl px-4">
      <h1 className="mb-6 text-2xl font-semibold">Report a problem</h1>
      <form onSubmit={onCheck} className="flex flex-col gap-5">
        <div>
          <label className="mb-1 block text-sm font-medium">
            What&apos;s the problem? (any language)
          </label>
          <textarea
            required
            minLength={5}
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Bada gaddha hai bus stop ke paas"
            className="w-full rounded-md border border-neutral-300 px-3 py-2"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">Where is it?</label>
          <LocationPicker value={location} onChange={setLocation} />
        </div>

        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="Nearby landmark (optional)"
          className="rounded-md border border-neutral-300 px-3 py-2"
        />

        <div>
          <label className="mb-1 block text-sm font-medium">Photo (optional)</label>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-neutral-900 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Checking…" : "Continue"}
        </button>
      </form>
    </main>
  );
}
