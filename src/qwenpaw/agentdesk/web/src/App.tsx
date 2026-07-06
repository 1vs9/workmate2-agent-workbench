import {
  ConfigProvider,
  bailianDarkTheme,
  bailianTheme,
} from "@agentscope-ai/design";
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
          ...(selectedTheme as { theme?: object }).theme,
          algorithm: isDark
            ? antdTheme.darkAlgorithm
            : antdTheme.defaultAlgorithm,
          token: {
            colorPrimary: "#059669",
            colorLink: "#059669",
            colorLinkHover: "#047857",
            borderRadius: 10,
            fontFamily:
              'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
          },
          components: {
            Button: {
              primaryShadow: "0 1px 2px rgba(5, 150, 105, 0.15)",
            },
            Card: {
              borderRadiusLG: 12,
            },
          },
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
