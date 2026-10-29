"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { api, setAccessToken, tryRefresh } from "./api";

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: "citizen" | "official" | "admin";
  preferred_language: string;
  department_id: number | null;
  is_department_head: boolean;
};

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On first load, try to restore the session from the refresh cookie.
  useEffect(() => {
    (async () => {
      if (await tryRefresh()) {
        try {
          setUser(await api.get<User>("/auth/me"));
        } catch {
          /* not logged in */
        }
      }
      setLoading(false);
    })();
  }, []);

  async function login(email: string, password: string) {
    const res = await api.post<{ access_token: string; user: User }>("/auth/login", {
      email,
      password,
    });
    setAccessToken(res.access_token);
    setUser(res.user);
    return res.user;
  }

  async function logout() {
    await api.post("/auth/logout").catch(() => {});
    setAccessToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
