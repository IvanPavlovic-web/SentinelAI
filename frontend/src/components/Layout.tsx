import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/videos", label: "Video Library" },
  { to: "/cameras", label: "Cameras & Zones" },
  { to: "/incidents", label: "Incidents" },
  { to: "/performance", label: "Performance" },
  { to: "/audit-logs", label: "Audit Logs", adminOnly: true },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-ops-bg text-slate-100 flex">
      <aside className="w-60 shrink-0 border-r border-ops-border bg-ops-panel flex flex-col">
        <div className="px-4 py-5 border-b border-ops-border">
          <h1 className="text-lg font-bold text-amber-400">SentinelAI</h1>
          <p className="text-xs text-slate-400">Edge Video Intelligence</p>
        </div>
        <nav className="flex-1 px-2 py-4 space-y-1">
          {navItems
            .filter((item) => !item.adminOnly || user?.role === "admin")
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `block rounded px-3 py-2 text-sm font-medium ${
                    isActive ? "bg-amber-500/10 text-amber-400" : "text-slate-300 hover:bg-slate-800"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
        </nav>
        <div className="border-t border-ops-border px-4 py-3 text-xs text-slate-400">
          <div className="mb-2">
            {user?.email} <span className="uppercase text-amber-400">({user?.role})</span>
          </div>
          <button onClick={handleLogout} className="text-red-400 hover:text-red-300">
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
