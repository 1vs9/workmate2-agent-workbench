# AgentDesk React Frontend — Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a new React + Vite SPA under `src/qwenpaw/agentdesk/web/` that builds, renders an app shell with routing/theme, and can be served by the FastAPI backend behind a dev flag — without touching the legacy frontend.

**Architecture:** New Vite app builds to `src/qwenpaw/agentdesk/static_next/`. FastAPI serves it via an SPA-fallback static mount, gated by `AGENTDESK_FRONTEND_NEXT=1` so the legacy `static/index.html` stays the default until cutover. Stack and config mirror QwenPaw Console (`console/`).

**Tech Stack:** React 18, Vite 6, TypeScript 5, Ant Design 5, `@agentscope-ai/design`, react-router-dom 7, zustand, dayjs, Vitest + React Testing Library.

---

## File structure

Created in this plan:
- `src/qwenpaw/agentdesk/web/package.json` — deps + scripts
- `src/qwenpaw/agentdesk/web/tsconfig.json` — TS config
- `src/qwenpaw/agentdesk/web/vite.config.ts` — build (outDir → `../static_next`), manualChunks, vitest
- `src/qwenpaw/agentdesk/web/index.html` — Vite entry HTML
- `src/qwenpaw/agentdesk/web/src/vite-env.d.ts` — env/global type decls
- `src/qwenpaw/agentdesk/web/src/api/config.ts` — API url + token helpers (ported from console)
- `src/qwenpaw/agentdesk/web/src/theme/ThemeContext.tsx` — light/dark theme context
- `src/qwenpaw/agentdesk/web/src/layouts/MainLayout.tsx` — sidebar + content shell
- `src/qwenpaw/agentdesk/web/src/pages/Home/index.tsx` — placeholder landing page
- `src/qwenpaw/agentdesk/web/src/router.tsx` — route table
- `src/qwenpaw/agentdesk/web/src/App.tsx` — providers + router shell
- `src/qwenpaw/agentdesk/web/src/main.tsx` — React root
- `src/qwenpaw/agentdesk/web/src/test/setup.ts` — Vitest DOM setup
- `src/qwenpaw/agentdesk/web/src/App.test.tsx` — smoke test
- `src/qwenpaw/agentdesk/web/.gitignore` — ignore node_modules/dist

Modified in this plan:
- `src/qwenpaw/agentdesk/settings.py` — add `get_next_frontend_dir()`
- `src/qwenpaw/agentdesk/frontend.py` — add SPA-fallback mount when `AGENTDESK_FRONTEND_NEXT=1`

---

## Task 1: Project manifest + install

**Files:**
- Create: `src/qwenpaw/agentdesk/web/package.json`
- Create: `src/qwenpaw/agentdesk/web/.gitignore`

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "agentdesk-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:run": "vitest run"
  },
  "dependencies": {
    "@agentscope-ai/design": "^1.0.14",
    "@ant-design/icons": "^5.0.1",
    "antd": "^5.29.1",
    "antd-style": "^3.7.1",
    "dayjs": "^1.11.13",
    "react": "^18",
    "react-dom": "^18",
    "react-router-dom": "^7.13.0",
    "zustand": "^5.0.3"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.9.1",
    "@testing-library/react": "^16.3.2",
    "@types/node": "^25.0.3",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "@vitejs/plugin-react": "^4.4.1",
    "jsdom": "^29.0.2",
    "less": "^4.5.1",
    "typescript": "~5.8.3",
    "vite": "^6.3.5",
    "vitest": "^4.1.4"
  }
}
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
node_modules/
dist/
*.local
.vite/
```

- [ ] **Step 3: Install dependencies**

Run: `cd src/qwenpaw/agentdesk/web && npm install`
Expected: completes with a `node_modules/` and `package-lock.json`. If `@agentscope-ai/design` resolves from a private registry that is unavailable, STOP and report — this is risk #2/#3 from the spec.

- [ ] **Step 4: Commit**

```bash
git add src/qwenpaw/agentdesk/web/package.json src/qwenpaw/agentdesk/web/.gitignore src/qwenpaw/agentdesk/web/package-lock.json
git commit -m "chore(agentdesk-web): scaffold package.json and install deps"
```

---

## Task 2: Build/TS config + entry HTML + env types

**Files:**
- Create: `src/qwenpaw/agentdesk/web/tsconfig.json`
- Create: `src/qwenpaw/agentdesk/web/vite.config.ts`
- Create: `src/qwenpaw/agentdesk/web/index.html`
- Create: `src/qwenpaw/agentdesk/web/src/vite-env.d.ts`

- [ ] **Step 1: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["node", "vitest/globals", "@testing-library/jest-dom"],
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"]
}
```

- [ ] **Step 2: Write `vite.config.ts`**

```typescript
/// <reference types="vitest" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Transform .css imports inside node_modules to empty stubs (e.g. @agentscope-ai/*).
const cssStubPlugin = {
  name: "css-stub",
  transform(_code: string, id: string) {
    if (id.includes("node_modules") && id.endsWith(".css")) {
      return { code: "export default {}" };
    }
  },
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBaseUrl = env.VITE_API_BASE_URL ?? "";

  return {
    define: {
      VITE_API_BASE_URL: JSON.stringify(apiBaseUrl),
      TOKEN: JSON.stringify(env.TOKEN || ""),
    },
    plugins: [react(), cssStubPlugin],
    css: {
      modules: {
        localsConvention: "camelCase",
        generateScopedName: "[name]__[local]__[hash:base64:5]",
      },
      preprocessorOptions: { less: { javascriptEnabled: true } },
    },
    resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
    server: {
      host: "0.0.0.0",
      port: 5174,
      proxy: {
        "/api": { target: "http://localhost:8088", changeOrigin: true },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: true,
    },
    build: {
      outDir: path.resolve(__dirname, "../static_next"),
      emptyOutDir: true,
      cssCodeSplit: true,
      sourcemap: mode !== "production",
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (
              id.includes("node_modules/react/") ||
              id.includes("node_modules/react-dom/") ||
              id.includes("node_modules/react-router-dom/") ||
              id.includes("node_modules/scheduler/")
            ) {
              return "react-vendor";
            }
            if (
              id.includes("node_modules/antd/") ||
              id.includes("node_modules/antd-style/") ||
              id.includes("node_modules/@ant-design/") ||
              id.includes("node_modules/@agentscope-ai/")
            ) {
              return "ui-vendor";
            }
            if (
              id.includes("node_modules/dayjs/") ||
              id.includes("node_modules/zustand/")
            ) {
              return "utils-vendor";
            }
          },
        },
      },
    },
  };
});
```

- [ ] **Step 3: Write `index.html`**

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0, viewport-fit=cover"
    />
    <title>AgentDesk</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Write `src/vite-env.d.ts`**

```typescript
/// <reference types="vite/client" />

declare const VITE_API_BASE_URL: string;
declare const TOKEN: string;
```

- [ ] **Step 5: Commit**

```bash
git add src/qwenpaw/agentdesk/web/tsconfig.json src/qwenpaw/agentdesk/web/vite.config.ts src/qwenpaw/agentdesk/web/index.html src/qwenpaw/agentdesk/web/src/vite-env.d.ts
git commit -m "chore(agentdesk-web): add vite/ts config and entry html"
```

---

## Task 3: API config (ported from console)

**Files:**
- Create: `src/qwenpaw/agentdesk/web/src/api/config.ts`

- [ ] **Step 1: Write `src/api/config.ts`**

```typescript
const AUTH_TOKEN_KEY = "qwenpaw_auth_token";

/** Full API URL with /api prefix. */
export function getApiUrl(path: string): string {
  const base = VITE_API_BASE_URL || "";
  const apiPrefix = "/api";
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${apiPrefix}${normalizedPath}`;
}

/** API token from localStorage (login) or build-time TOKEN. */
export function getApiToken(): string {
  const stored = localStorage.getItem(AUTH_TOKEN_KEY);
  if (stored) return stored;
  return typeof TOKEN !== "undefined" ? TOKEN : "";
}

export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/qwenpaw/agentdesk/web/src/api/config.ts
git commit -m "feat(agentdesk-web): add api config helpers"
```

---

## Task 4: Theme context, layout, home page, router, App, main

**Files:**
- Create: `src/qwenpaw/agentdesk/web/src/theme/ThemeContext.tsx`
- Create: `src/qwenpaw/agentdesk/web/src/layouts/MainLayout.tsx`
- Create: `src/qwenpaw/agentdesk/web/src/pages/Home/index.tsx`
- Create: `src/qwenpaw/agentdesk/web/src/router.tsx`
- Create: `src/qwenpaw/agentdesk/web/src/App.tsx`
- Create: `src/qwenpaw/agentdesk/web/src/main.tsx`

- [ ] **Step 1: Write `src/theme/ThemeContext.tsx`**

```tsx
import { createContext, useContext, useEffect, useState } from "react";

interface ThemeContextValue {
  isDark: boolean;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  isDark: false,
  toggle: () => {},
});

const STORAGE_KEY = "agentdesk_theme_dark";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [isDark, setIsDark] = useState<boolean>(
    () => localStorage.getItem(STORAGE_KEY) === "1",
  );

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, isDark ? "1" : "0");
  }, [isDark]);

  return (
    <ThemeContext.Provider value={{ isDark, toggle: () => setIsDark((v) => !v) }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
```

- [ ] **Step 2: Write `src/pages/Home/index.tsx`**

```tsx
import { Typography } from "antd";

export default function HomePage() {
  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>AgentDesk</Typography.Title>
      <Typography.Paragraph>
        React frontend scaffold is running.
      </Typography.Paragraph>
    </div>
  );
}
```

- [ ] **Step 3: Write `src/layouts/MainLayout.tsx`**

```tsx
import { Layout, Menu } from "antd";
import { useNavigate, useLocation, Outlet } from "react-router-dom";

const navItems = [{ key: "/", label: "首页" }];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider theme="light" width={220}>
        <div style={{ height: 56, display: "flex", alignItems: "center", paddingLeft: 24, fontWeight: 600 }}>
          AgentDesk
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={navItems}
          onClick={({ key }) => navigate(key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Content>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
```

- [ ] **Step 4: Write `src/router.tsx`**

```tsx
import { Routes, Route } from "react-router-dom";
import MainLayout from "./layouts/MainLayout";
import HomePage from "./pages/Home";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<HomePage />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 5: Write `src/App.tsx`**

```tsx
import { ConfigProvider, bailianDarkTheme, bailianTheme } from "@agentscope-ai/design";
import { App as AntdApp, theme as antdTheme } from "antd";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, useTheme } from "./theme/ThemeContext";
import AppRoutes from "./router";

function AppInner() {
  const { isDark } = useTheme();
  const selectedTheme = isDark ? bailianDarkTheme : bailianTheme;

  return (
    <BrowserRouter>
      <ConfigProvider
        {...selectedTheme}
        prefix="qwenpaw"
        prefixCls="qwenpaw"
        theme={{
          ...(selectedTheme as any)?.theme,
          algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
          token: { colorPrimary: "#FF7F16" },
        }}
      >
        <AntdApp>
          <AppRoutes />
        </AntdApp>
      </ConfigProvider>
    </BrowserRouter>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AppInner />
    </ThemeProvider>
  );
}
```

- [ ] **Step 6: Write `src/main.tsx`**

```tsx
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(<App />);
```

- [ ] **Step 7: Type-check**

Run: `cd src/qwenpaw/agentdesk/web && npx tsc --noEmit`
Expected: no errors. If `@agentscope-ai/design` lacks `bailianTheme`/`bailianDarkTheme` exports, STOP and inspect the package's actual exports (`node_modules/@agentscope-ai/design`).

- [ ] **Step 8: Commit**

```bash
git add src/qwenpaw/agentdesk/web/src
git commit -m "feat(agentdesk-web): add app shell, theme, layout, router, home page"
```

---

## Task 5: Test setup + App smoke test

**Files:**
- Create: `src/qwenpaw/agentdesk/web/src/test/setup.ts`
- Create: `src/qwenpaw/agentdesk/web/src/App.test.tsx`

- [ ] **Step 1: Write `src/test/setup.ts`**

```typescript
import "@testing-library/jest-dom";

// jsdom lacks matchMedia, which antd reads at module init.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}
```

- [ ] **Step 2: Write the failing test `src/App.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the AgentDesk home page", () => {
    render(<App />);
    expect(
      screen.getByText("React frontend scaffold is running."),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd src/qwenpaw/agentdesk/web && npx vitest run src/App.test.tsx`
Expected: 1 passed. (If antd/@agentscope-ai pull in CSS or matchMedia errors, the `css-stub` plugin + `setup.ts` matchMedia shim should resolve them; if a heavy `@agentscope-ai/design` import OOMs the test worker, add a `vi.mock("@agentscope-ai/design", ...)` returning `ConfigProvider` passthrough + empty theme objects, mirroring console's `src/test/design-mock.ts`.)

- [ ] **Step 4: Commit**

```bash
git add src/qwenpaw/agentdesk/web/src/test/setup.ts src/qwenpaw/agentdesk/web/src/App.test.tsx
git commit -m "test(agentdesk-web): add vitest setup and App smoke test"
```

---

## Task 6: Production build → static_next

**Files:**
- Output: `src/qwenpaw/agentdesk/static_next/` (generated; not committed)

- [ ] **Step 1: Build**

Run: `cd src/qwenpaw/agentdesk/web && npm run build`
Expected: build succeeds; `src/qwenpaw/agentdesk/static_next/index.html` and `static_next/assets/*.js|css` exist.

- [ ] **Step 2: Verify output**

Run: `ls src/qwenpaw/agentdesk/static_next && ls src/qwenpaw/agentdesk/static_next/assets`
Expected: `index.html` present; assets include `react-vendor`, `ui-vendor` chunks.

- [ ] **Step 3: Ignore build output in git**

Add `static_next/` to `.gitignore` at the agentdesk package level. Edit `src/qwenpaw/agentdesk/.gitignore` (create if missing) to contain:

```gitignore
static_next/
```

- [ ] **Step 4: Commit**

```bash
git add src/qwenpaw/agentdesk/.gitignore
git commit -m "chore(agentdesk): ignore generated static_next build output"
```

---

## Task 7: Backend serves static_next behind a flag (SPA fallback)

**Files:**
- Modify: `src/qwenpaw/agentdesk/settings.py`
- Modify: `src/qwenpaw/agentdesk/frontend.py`

- [ ] **Step 1: Add `get_next_frontend_dir()` to `settings.py`**

Add after `_BUNDLED_STATIC_DIR = _PKG_DIR / "static"` (line 10):

```python
_BUNDLED_STATIC_NEXT_DIR = _PKG_DIR / "static_next"
```

Add this function after `get_bundled_frontend_dir()`:

```python
def get_next_frontend_dir() -> Path | None:
    """New React (Vite) build, served only when AGENTDESK_FRONTEND_NEXT is on."""
    raw = os.environ.get("AGENTDESK_FRONTEND_NEXT", "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return None
    if (
        _BUNDLED_STATIC_NEXT_DIR.is_dir()
        and (_BUNDLED_STATIC_NEXT_DIR / "index.html").is_file()
    ):
        return _BUNDLED_STATIC_NEXT_DIR
    return None
```

- [ ] **Step 2: Add SPA-fallback mount to `frontend.py`**

Replace the imports block (lines 9-13) with:

```python
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .settings import get_frontend_dir, get_next_frontend_dir
```

Add this class just above `def mount_agentdesk_frontend`:

```python
class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise
```

Replace the body of `mount_agentdesk_frontend` (the part starting at `frontend_dir = get_frontend_dir()`) so the new build wins when its flag is set:

```python
    next_dir = get_next_frontend_dir()
    frontend_dir = next_dir or get_frontend_dir()
    if frontend_dir is None:
        return False

    index = frontend_dir / "index.html"
    if not index.is_file():
        logger.warning(
            "AgentDesk frontend dir %s has no index.html; skip mount",
            frontend_dir,
        )
        return False

    register_legacy_qwenpaw_ui_redirects(app)
    if next_dir is not None:
        app.mount(
            "/",
            SPAStaticFiles(directory=str(frontend_dir), html=True),
            name="agentdesk_frontend",
        )
        logger.info("AgentDesk React frontend mounted from %s", frontend_dir)
    else:
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dir), html=True),
            name="agentdesk_frontend",
        )
        logger.info("AgentDesk frontend mounted from %s", frontend_dir)
    return True
```

- [ ] **Step 3: Verify legacy path unchanged (flag off)**

Run: `cd D:/proj/workbuddy && python -c "import os; os.environ.pop('AGENTDESK_FRONTEND_NEXT', None); from qwenpaw.agentdesk.settings import get_next_frontend_dir; print(get_next_frontend_dir())"`
Expected: `None` (legacy `static/` still serves by default).

- [ ] **Step 4: Verify new build resolves (flag on)**

Run: `cd D:/proj/workbuddy && AGENTDESK_FRONTEND_NEXT=1 python -c "from qwenpaw.agentdesk.settings import get_next_frontend_dir; print(get_next_frontend_dir())"`
Expected: prints the absolute path to `.../agentdesk/static_next` (requires Task 6 build present).

- [ ] **Step 5: Manual smoke test (flag on)**

Run the backend with `AGENTDESK_FRONTEND_NEXT=1` and open `/`. Expected: the React shell renders ("AgentDesk" sidebar + home text). Navigate to a deep client route (e.g. `/nonexistent`) and confirm `index.html` is returned (SPA fallback) rather than a 404.

- [ ] **Step 6: Commit**

```bash
git add src/qwenpaw/agentdesk/settings.py src/qwenpaw/agentdesk/frontend.py
git commit -m "feat(agentdesk): serve React build behind AGENTDESK_FRONTEND_NEXT flag with SPA fallback"
```

---

## Self-Review

**Spec coverage (scaffold scope of §3/§4/§6 of the design spec):**
- New app at `web/`, build to `static_next/` → Tasks 1-2, 6 ✓
- Mirror console stack (React/Vite/antd/@agentscope-ai/design, manualChunks) → Tasks 1-2 ✓
- App shell with theme + router (mirror `App.tsx`) → Task 4 ✓
- API config reuse (`getApiUrl`/token) → Task 3 ✓
- Serve via FastAPI with SPA history fallback, behind flag, legacy untouched → Task 7 ✓
- Vitest + RTL setup → Task 5 ✓
- Dev proxy for `/api` → Task 2 (vite server.proxy) ✓

Out of scope here (later plans): chat (`AgentScopeRuntimeWebUI`), i18n, all AgentDesk feature pages, cutover/retire legacy.

**Placeholder scan:** No TBD/TODO; every code step contains full file contents or exact edit anchors.

**Type consistency:** `useTheme()` returns `{ isDark, toggle }` (Task 4 step 1) and is consumed as `{ isDark }` (Task 4 step 5) ✓. `get_next_frontend_dir()` defined in Task 7 step 1 and imported in step 2 ✓. `getApiUrl`/`getApiToken` defined Task 3, unused in scaffold (used by later page plans) — acceptable foundation, not a dangling reference.

**Known external risks to surface during execution:** `@agentscope-ai/design` registry availability + actual export names (`bailianTheme`/`bailianDarkTheme`); potential vitest OOM from heavy design package (mitigation noted in Task 5 step 3).
