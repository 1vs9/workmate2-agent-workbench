import { Outlet, useLocation } from "react-router-dom";
import AppSidebar from "../components/layout/AppSidebar";
import PageShell from "../components/layout/PageShell";

const PAGE_ROUTES = new Set([
  "/plaza",
  "/team",
  "/skills",
  "/cases",
  "/knowledge",
  "/mcp",
  "/automation",
  "/settings",
]);

export default function MainLayout() {
  const location = useLocation();
  const usePageShell = PAGE_ROUTES.has(location.pathname);

  return (
    <div className="flex h-screen overflow-hidden bg-[#f8faf9] text-gray-700 antialiased">
      <AppSidebar />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#f8faf9]">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {usePageShell ? (
            <PageShell narrow={location.pathname === "/settings"}>
              <Outlet />
            </PageShell>
          ) : (
            <Outlet />
          )}
        </div>
      </main>
    </div>
  );
}
