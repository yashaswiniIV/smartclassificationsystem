"use client";

import Link from "next/link";

import { NotificationsBell } from "@/components/NotificationsBell";
import { useAuth } from "@/lib/auth";

export function Nav() {
  const { user, logout, loading } = useAuth();
  const isStaff = user?.role === "official" || user?.role === "admin";
  return (
    <nav className="sticky top-0 z-30 flex items-center justify-between border-b border-neutral-200 bg-white/90 px-6 py-3 backdrop-blur">
      <Link href="/" className="text-lg font-semibold">
        CivicPulse AI
      </Link>
      <div className="flex items-center gap-4 text-sm">
        {isStaff ? (
          <>
            <Link href="/console" className="hover:underline">
              Console
            </Link>
            <Link href="/console/analytics" className="hover:underline">
              Analytics
            </Link>
            <Link href="/console/predictive" className="hover:underline">
              Predictive
            </Link>
            <Link href="/console/reports" className="hover:underline">
              Reports
            </Link>
          </>
        ) : (
          <>
            <Link href="/report" className="hover:underline">
              Report
            </Link>
            <Link href="/my" className="hover:underline">
              My complaints
            </Link>
          </>
        )}
        <Link href="/public" className="hover:underline">
          Transparency
        </Link>
        {loading ? null : user ? (
          <>
            <NotificationsBell />
            <span className="text-neutral-500">{user.full_name}</span>
            <button onClick={logout} className="rounded-md border px-3 py-1 hover:bg-neutral-100">
              Logout
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="hover:underline">
              Login
            </Link>
            <Link
              href="/signup"
              className="rounded-md border px-3 py-1 hover:bg-neutral-100"
            >
              Sign up
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}
