const COLORS: Record<string, string> = {
  open: "bg-neutral-100 text-neutral-700",
  acknowledged: "bg-blue-100 text-blue-700",
  assigned: "bg-indigo-100 text-indigo-700",
  in_progress: "bg-amber-100 text-amber-800",
  resolved: "bg-green-100 text-green-700",
  closed: "bg-neutral-200 text-neutral-600",
  reopened: "bg-orange-100 text-orange-700",
  rejected: "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = COLORS[status] ?? "bg-neutral-100 text-neutral-700";
  return (
    <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status.replace("_", " ")}
    </span>
  );
}
