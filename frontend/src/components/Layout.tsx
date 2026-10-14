import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/cameras", label: "Cameras" },
  { to: "/videos", label: "Video Library" },
  { to: "/incidents", label: "Incidents" },
  { to: "/performance", label: "Performance" },
  { to: "/audit-logs", label: "Audit Logs", adminOnly: true },
];

const roleColor: Record<string, string> = {
  admin: "text-status-critical border-status-critical/40",
  analyst: "text-ops-accent border-ops-accent/40",
  viewer: "text-status-ok border-status-ok/40",
};

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-ops-bg text-slate-100 flex">
      <aside className="w-64 shrink-0 border-r border-ops-border bg-ops-panel flex flex-col">
        <div className="px-5 py-5 border-b border-ops-border flex items-center gap-2.5">
          <svg viewBox="0 0 24 24" className="w-6 h-6 text-ops-accent shrink-0" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2l8 3v6c0 5-3.5 8.5-8 11-4.5-2.5-8-6-8-11V5z" />
          </svg>
          <div>
            <h1 className="font-display text-base font-semibold tracking-tight leading-none">SentinelAI</h1>
            <p className="text-[11px] text-slate-500 mt-0.5 tracking-wide">Edge Video Intelligence</p>
          </div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {navItems
            .filter((item) => !item.adminOnly || user?.role === "admin")
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium border-l-2 transition-colors ${
                    isActive
                      ? "bg-ops-accent/10 text-ops-accent border-ops-accent"
                      : "text-slate-400 border-transparent hover:bg-white/[0.03] hover:text-slate-200"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
        </nav>
        <div className="border-t border-ops-border px-4 py-3.5">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-xs text-slate-400 truncate">{user?.email}</span>
            <span className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border ${roleColor[user?.role ?? ""] ?? "text-slate-400 border-ops-border"}`}>
              {user?.role}
            </span>
          </div>
          <button
            onClick={handleLogout}
            className="text-xs text-slate-500 hover:text-status-critical transition-colors"
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
