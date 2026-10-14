import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register(email, password, fullName);
      navigate("/");
    } catch {
      setError("Registration failed. Email may already be in use.");
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
          <h1 className="text-lg font-semibold mb-6">Create account</h1>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="register-name" className="block text-xs text-slate-400 mb-1.5">Full name</label>
              <input
                id="register-name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="w-full rounded-md bg-ops-panel2 border border-ops-border px-3 py-2.5 text-sm transition-colors focus:outline-none focus:border-ops-accent"
              />
            </div>
            <div>
              <label htmlFor="register-email" className="block text-xs text-slate-400 mb-1.5">Email</label>
              <input
                id="register-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-md bg-ops-panel2 border border-ops-border px-3 py-2.5 text-sm transition-colors focus:outline-none focus:border-ops-accent"
              />
            </div>
            <div>
              <label htmlFor="register-password" className="block text-xs text-slate-400 mb-1.5">Password</label>
              <input
                id="register-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="w-full rounded-md bg-ops-panel2 border border-ops-border px-3 py-2.5 text-sm transition-colors focus:outline-none focus:border-ops-accent"
              />
            </div>
            {error && <p className="text-xs text-status-critical">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-ops-accent text-ops-bg font-semibold py-2.5 text-sm transition-colors hover:bg-ops-accentDim disabled:opacity-50"
            >
              {submitting ? "Creating…" : "Create account"}
            </button>
          </form>
          <p className="text-xs text-slate-500 mt-5 text-center">
            Already have an account?{" "}
            <Link to="/login" className="text-ops-accent hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
