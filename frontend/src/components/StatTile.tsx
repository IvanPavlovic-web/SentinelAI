interface StatTileProps {
  label: string;
  value: string | number;
  accent?: "default" | "amber" | "red" | "green";
}

const accentText: Record<string, string> = {
  default: "text-slate-100",
  amber: "text-status-high",
  red: "text-status-critical",
  green: "text-status-ok",
};

const accentBar: Record<string, string> = {
  default: "bg-ops-borderStrong",
  amber: "bg-status-high",
  red: "bg-status-critical",
  green: "bg-status-ok",
};

export default function StatTile({ label, value, accent = "default" }: StatTileProps) {
  return (
    <div className="relative bg-ops-panel border border-ops-border rounded-lg px-5 py-4 overflow-hidden">
      <span className={`absolute inset-x-0 top-0 h-0.5 ${accentBar[accent]}`} />
      <p className="text-[11px] uppercase tracking-widest2 text-slate-500 mb-1.5 font-medium">{label}</p>
      <p className={`tabular text-[1.7rem] font-medium leading-none ${accentText[accent]}`}>{value}</p>
    </div>
  );
}
