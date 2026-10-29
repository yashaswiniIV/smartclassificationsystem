"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth";

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5">
      <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-neutral-900 text-sm font-medium text-white">
        {n}
      </div>
      <h3 className="font-medium">{title}</h3>
      <p className="mt-1 text-sm text-neutral-500">{body}</p>
    </div>
  );
}

export default function Home() {
  const { user } = useAuth();
  const isStaff = user?.role === "official" || user?.role === "admin";

  return (
    <main className="mx-auto max-w-4xl px-4">
      <section className="mt-16 text-center">
        <p className="mb-3 inline-block rounded-full bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-600">
          Pilot city: Bengaluru
        </p>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          Civic complaints, turned into action.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-neutral-600">
          Report a problem in seconds. CivicPulse deduplicates it with AI, routes it to the
          right department, and tracks it to resolution — with city-wide intelligence for
          officials.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          {isStaff ? (
            <Link
              href="/console"
              className="rounded-md bg-neutral-900 px-5 py-2.5 text-white hover:bg-neutral-800"
            >
              Open console
            </Link>
          ) : (
            <>
              <Link
                href="/report"
                className="rounded-md bg-neutral-900 px-5 py-2.5 text-white hover:bg-neutral-800"
              >
                Report a problem
              </Link>
              <Link
                href="/my"
                className="rounded-md border border-neutral-300 bg-white px-5 py-2.5 hover:bg-neutral-100"
              >
                Track my complaints
              </Link>
            </>
          )}
          <Link
            href="/public"
            className="rounded-md border border-neutral-300 bg-white px-5 py-2.5 hover:bg-neutral-100"
          >
            View city transparency
          </Link>
        </div>
      </section>

      <section className="mt-16 grid gap-4 sm:grid-cols-3">
        <Step
          n={1}
          title="Report"
          body="Drop a pin, describe it in any language, add a photo. We check if it's already reported."
        />
        <Step
          n={2}
          title="AI triages"
          body="Multilingual dedup, auto-categorization, photo analysis, and priority — in seconds."
        />
        <Step
          n={3}
          title="Resolved & tracked"
          body="The right department acts; you get updates and confirm the fix."
        />
      </section>

      <section className="my-16 rounded-xl border border-neutral-200 bg-white p-6">
        <h2 className="text-lg font-medium">Built for three roles</h2>
        <div className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <p className="font-medium">Citizens</p>
            <p className="mt-1 text-neutral-500">
              Report, avoid duplicates, and follow issues to resolution.
            </p>
          </div>
          <div>
            <p className="font-medium">Officials</p>
            <p className="mt-1 text-neutral-500">
              A prioritized, deduplicated queue with audit trails and SLAs.
            </p>
          </div>
          <div>
            <p className="font-medium">Administrators</p>
            <p className="mt-1 text-neutral-500">
              Heatmaps, trends, emerging-hotspot forecasts, and weekly reports.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
