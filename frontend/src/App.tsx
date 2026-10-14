import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import VideoLibrary from "./pages/VideoLibrary";
import VideoDetail from "./pages/VideoDetail";
import Incidents from "./pages/Incidents";
import Performance from "./pages/Performance";
import AuditLogs from "./pages/AuditLogs";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/videos" element={<VideoLibrary />} />
          <Route path="/videos/:id" element={<VideoDetail />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/audit-logs" element={<AuditLogs />} />
        </Route>
      </Route>
    </Routes>
  );
}
