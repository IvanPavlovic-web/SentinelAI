import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const [email, setEmail] = useState("admin@sentinelai.dev");
  const [password, setPassword] = useState("Admin123!");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      setError("Invalid credentials. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-ops-bg px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2.5 mb-7 justify-center">
          <svg viewBox="0 0 24 24" className="w-7 h-7 text-ops-accent" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2l8 3v6c0 5-3.5 8.5-8 11-4.5-2.5-8-6-8-11V5z" />
          </svg>
          <span className="font-display text-xl font-semibold">SentinelAI</span>
        </div>

        <div className="bg-ops-panel border border-ops-border rounded-lg p-8">
          <p className="text-[11px] uppercase tracking-widest2 text-slate-500 mb-1">Operations Console</p>
          <h1 className="text-lg font-semibold mb-6">Sign in to continue</h1>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="block text-xs text-slate-400 mb-1.5">Email</label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-md bg-ops-panel2 border border-ops-border px-3 py-2.5 text-sm transition-colors focus:outline-none focus:border-ops-accent"
              />
            </div>
            <div>
              <label htmlFor="login-password" className="block text-xs text-slate-400 mb-1.5">Password</label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full rounded-md bg-ops-panel2 border border-ops-border px-3 py-2.5 text-sm transition-colors focus:outline-none focus:border-ops-accent"
              />
            </div>
            {error && <p className="text-xs text-status-critical">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-ops-accent text-ops-bg font-semibold py-2.5 text-sm transition-colors hover:bg-ops-accentDim disabled:opacity-50"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="text-xs text-slate-500 mt-5 text-center">
            No account?{" "}
            <Link to="/register" className="text-ops-accent hover:underline">
              Register
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
