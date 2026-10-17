import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import RequireAuth from "@/components/RequireAuth";
import HomePage from "@/pages/HomePage";
import AuthPage from "@/pages/AuthPage";
import ProfilePage from "@/pages/ProfilePage";
import MatchesPage from "@/pages/MatchesPage";
import DirectoryPage from "@/pages/DirectoryPage";
import RoleDetailPage from "@/pages/RoleDetailPage";
import JobsPage from "@/pages/JobsPage";
import ApplicationsPage from "@/pages/ApplicationsPage";
import ComparePage from "@/pages/ComparePage";
import RoadmapPage from "@/pages/RoadmapPage";
import RoadmapsPage from "@/pages/RoadmapsPage";
import TrackerPage from "@/pages/TrackerPage";
import ChatPage from "@/pages/ChatPage";
import NotFoundPage from "@/pages/NotFoundPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/matches" element={<MatchesPage />} />
        <Route path="/roles" element={<DirectoryPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/roles/:roleId" element={<RoleDetailPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/roadmap/:roleId" element={<RoadmapPage />} />
        <Route path="/roadmaps" element={<RequireAuth><RoadmapsPage /></RequireAuth>} />
        <Route path="/tracker" element={<RequireAuth><TrackerPage /></RequireAuth>} />
        <Route path="/tracker/:roleId" element={<RequireAuth><TrackerPage /></RequireAuth>} />
        <Route
          path="/applications"
          element={
            <RequireAuth>
              <ApplicationsPage />
            </RequireAuth>
          }
        />
        <Route path="/chat/:roleId" element={<ChatPage />} />
        <Route path="/directory" element={<Navigate to="/roles" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}
