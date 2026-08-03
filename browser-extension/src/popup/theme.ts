import type { ExtensionSettings } from "../shared/types";

export function applyTheme(theme: ExtensionSettings["theme"]): void {
  const resolved =
    theme === "system" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;
  document.documentElement.dataset.theme = resolved;
}
