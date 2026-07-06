import { Routes, Route, Navigate } from "react-router-dom";
import MainLayout from "./layouts/MainLayout";
import HomePage from "./pages/Home";
import TaskChatPage from "./pages/TaskChat";
import PlazaPage from "./pages/Plaza";
import TeamPage from "./pages/Team";
import SkillsPage from "./pages/Skills";
import McpPage from "./pages/Mcp";
import AutomationPage from "./pages/Automation";
import SettingsPage from "./pages/Settings";
import DocLibrary from "./pages/DocLibrary";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<HomePage />} />
        <Route path="task/:taskId" element={<TaskChatPage />} />
        <Route path="chat" element={<Navigate to="/" replace />} />
        <Route path="plaza" element={<PlazaPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route
          path="cases"
          element={
            <DocLibrary
              kind="cases"
              title="案例库"
              subtitle="沉淀可复用的工作案例"
            />
          }
        />
        <Route
          path="knowledge"
          element={
            <DocLibrary
              kind="knowledge"
              title="资料库"
              subtitle="团队共享的知识资料"
            />
          }
        />
        <Route path="mcp" element={<McpPage />} />
        <Route path="automation" element={<AutomationPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
