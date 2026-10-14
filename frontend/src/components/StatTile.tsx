interface StatTileProps {
  label: string;
  value: string | number;
  accent?: "default" | "amber" | "red" | "green";
}

const accentClasses: Record<string, string> = {
  default: "text-slate-100",
  amber: "text-amber-400",
  red: "text-red-400",
  green: "text-emerald-400",
};

export default function StatTile({ label, value, accent = "default" }: StatTileProps) {
  return (
    <div className="bg-ops-panel border border-ops-border rounded-lg px-5 py-4">
      <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${accentClasses[accent]}`}>{value}</p>
    </div>
  );
}
