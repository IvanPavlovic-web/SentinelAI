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
    <div className="min-h-screen flex items-center justify-center bg-ops-bg">
      <div className="w-full max-w-sm bg-ops-panel border border-ops-border rounded-lg p-8">
        <h1 className="text-xl font-bold text-amber-400 mb-1">Create account</h1>
        <p className="text-sm text-slate-400 mb-6">Join SentinelAI as a viewer</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Full name</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm focus:outline-none focus:border-amber-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm focus:outline-none focus:border-amber-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm focus:outline-none focus:border-amber-500"
            />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded bg-amber-500 text-slate-950 font-semibold py-2 text-sm hover:bg-amber-400 disabled:opacity-50"
          >
            {submitting ? "Creating..." : "Create account"}
          </button>
        </form>
        <p className="text-xs text-slate-400 mt-4">
          Already have an account?{" "}
          <Link to="/login" className="text-amber-400 hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
