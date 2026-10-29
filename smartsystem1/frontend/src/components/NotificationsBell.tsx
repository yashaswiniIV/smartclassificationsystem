"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";

type Notification = {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  issue_id: string | null;
  read_at: string | null;
  created_at: string;
};

export function NotificationsBell() {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const unread = items.filter((n) => !n.read_at).length;

  const load = useCallback(async () => {
    try {
      setItems(await api.get<Notification[]>("/notifications"));
    } catch {
      /* not logged in / transient */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000); // light polling; websockets are a later upgrade
    return () => clearInterval(t);
  }, [load]);

  async function markAllRead() {
    await api.post("/notifications/read", {}).catch(() => {});
    await load();
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        className="relative rounded-md px-2 py-1 hover:bg-neutral-100"
      >
        <span aria-hidden>🔔</span>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-medium text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-md border border-neutral-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-medium">Notifications</span>
            {unread > 0 && (
              <button onClick={markAllRead} className="text-xs text-blue-600 hover:underline">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-neutral-400">Nothing yet</p>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  className={`border-b px-3 py-2 text-sm last:border-0 ${
                    n.read_at ? "bg-white" : "bg-blue-50"
                  }`}
                >
                  <p className="font-medium text-neutral-800">{n.title}</p>
                  {n.body && <p className="text-neutral-500">{n.body}</p>}
                  <p className="mt-0.5 text-xs text-neutral-400">
                    {new Date(n.created_at).toLocaleString()}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
