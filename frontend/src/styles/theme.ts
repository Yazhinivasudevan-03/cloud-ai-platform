import { createTheme, type PaletteMode } from "@mui/material";

/** Central MUI theme factory - one source of truth for light/dark mode so
 * every page/component picks up the same palette rather than hardcoding
 * colors. */
export function createAppTheme(mode: PaletteMode) {
  return createTheme({
    palette: {
      mode,
      primary: { main: "#3f6fd1" },
      secondary: { main: "#00a884" },
      background:
        mode === "dark"
          ? { default: "#0f1620", paper: "#161f2c" }
          : { default: "#f4f6f8", paper: "#ffffff" },
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: [
        "Inter",
        "-apple-system",
        "BlinkMacSystemFont",
        "Segoe UI",
        "Roboto",
        "Helvetica Neue",
        "Arial",
        "sans-serif",
      ].join(","),
      h4: { fontWeight: 700 },
      h5: { fontWeight: 700 },
      h6: { fontWeight: 600 },
    },
    components: {
      MuiPaper: {
        defaultProps: { elevation: 0 },
        styleOverrides: {
          root: ({ theme }) => ({
            border: `1px solid ${theme.palette.divider}`,
          }),
        },
      },
      MuiButton: {
        styleOverrides: {
          root: { textTransform: "none", fontWeight: 600 },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          head: { fontWeight: 700 },
        },
      },
    },
  });
}
