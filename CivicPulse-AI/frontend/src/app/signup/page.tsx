"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PasswordInput } from "@/components/PasswordInput";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type RegisterResp = { status: string; dev_otp?: string };

export default function SignupPage() {
  const { login } = useAuth();
  const router = useRouter();

  // Two steps: collect details, then verify the emailed 6-digit code.
  const [step, setStep] = useState<"details" | "verify">("details");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const resp = await api.post<RegisterResp>("/auth/register", {
        full_name: fullName,
        email,
        password,
      });
      // In dev the backend returns the code so you don't need the email.
      if (resp.dev_otp) {
        setDevOtp(resp.dev_otp);
        setOtp(resp.dev_otp);
      }
      setStep("verify");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign up failed");
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.post("/auth/verify-email", { email, otp });
      // Verified — log straight in and go report something.
      await login(email, password);
      router.push("/report");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setError(null);
    setBusy(true);
    try {
      // Re-calling register re-issues a fresh code for an unverified email.
      const resp = await api.post<RegisterResp>("/auth/register", {
        full_name: fullName,
        email,
        password,
      });
      if (resp.dev_otp) {
        setDevOtp(resp.dev_otp);
        setOtp(resp.dev_otp);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resend code");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto mt-16 max-w-sm px-4">
      <h1 className="mb-2 text-2xl font-semibold">
        {step === "details" ? "Create your account" : "Verify your email"}
      </h1>

      {step === "details" ? (
        <>
          <p className="mb-6 text-sm text-neutral-500">
            Citizens sign up here to report and track civic problems.
          </p>
          <form onSubmit={onRegister} className="flex flex-col gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium">Full name</label>
              <input
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name"
                autoComplete="name"
                className="w-full rounded-md border border-neutral-300 px-3 py-2"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                className="w-full rounded-md border border-neutral-300 px-3 py-2"
              />
              <p className="mt-1 text-xs text-neutral-400">
                We&apos;ll send a 6-digit code here to confirm it&apos;s you.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Password</label>
              <PasswordInput
                value={password}
                onChange={setPassword}
                autoComplete="new-password"
                minLength={8}
                placeholder="At least 8 characters"
              />
              <p className="mt-1 text-xs text-neutral-400">Minimum 8 characters.</p>
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-neutral-900 px-4 py-2 text-white disabled:opacity-50"
            >
              {busy ? "Creating…" : "Create account"}
            </button>
          </form>
          <p className="mt-4 text-sm text-neutral-500">
            Already have an account?{" "}
            <Link href="/login" className="underline">
              Log in
            </Link>
          </p>
        </>
      ) : (
        <>
          <p className="mb-6 text-sm text-neutral-500">
            Enter the 6-digit code we sent to <span className="font-medium">{email}</span>.
          </p>
          {devOtp && (
            <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Dev mode: your code is <span className="font-mono font-medium">{devOtp}</span>{" "}
              (already filled in below).
            </p>
          )}
          <form onSubmit={onVerify} className="flex flex-col gap-4">
            <input
              required
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="123456"
              className="w-full rounded-md border border-neutral-300 px-3 py-2 text-center font-mono text-lg tracking-widest"
            />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-neutral-900 px-4 py-2 text-white disabled:opacity-50"
            >
              {busy ? "Verifying…" : "Verify & continue"}
            </button>
          </form>
          <div className="mt-4 flex items-center justify-between text-sm text-neutral-500">
            <button onClick={onResend} disabled={busy} className="underline disabled:opacity-50">
              Resend code
            </button>
            <Link href="/login" className="underline">
              Already verified? Log in
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
