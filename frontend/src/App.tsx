import { Suspense, lazy } from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

// Every page is its own chunk, fetched only when its route is actually
// visited. Without this, the initial load pulled in every page's code
// up front -- including recharts (used by only 3 of 10 pages, and the
// single heaviest dependency in the app) -- as one ~722KB bundle, so even
// opening the Login page downloaded the charting library before it was
// ever needed.
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const VideoLibrary = lazy(() => import("./pages/VideoLibrary"));
const VideoDetail = lazy(() => import("./pages/VideoDetail"));
const Cameras = lazy(() => import("./pages/Cameras"));
const CameraDetail = lazy(() => import("./pages/CameraDetail"));
const Incidents = lazy(() => import("./pages/Incidents"));
const Performance = lazy(() => import("./pages/Performance"));
const Analytics = lazy(() => import("./pages/Analytics"));
const AuditLogs = lazy(() => import("./pages/AuditLogs"));

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-ops-bg">
      <div className="w-5 h-5 rounded-full border-2 border-ops-border border-t-ops-accent animate-spin" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cameras" element={<Cameras />} />
            <Route path="/cameras/:id" element={<CameraDetail />} />
            <Route path="/videos" element={<VideoLibrary />} />
            <Route path="/videos/:id" element={<VideoDetail />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/performance" element={<Performance />} />
            <Route path="/audit-logs" element={<AuditLogs />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
