import { logout } from "../shared/auth";
import { getSettings, getTokens } from "../shared/storage";
import { applyTheme } from "./theme";
import { renderLogin } from "./views/login-view";
import { renderDashboard } from "./views/dashboard-view";
import { renderSettings } from "./views/settings-view";

const app = document.getElementById("app")!;

function showLogin(): void {
  renderLogin(app, showDashboard);
}

function showDashboard(): void {
  void renderDashboard(app, { onOpenSettings: showSettings, onLogout: doLogout });
}

function showSettings(): void {
  void renderSettings(app, { onBack: showDashboard, onLogout: doLogout });
}

function doLogout(): void {
  void logout().then(showLogin);
}

async function init(): Promise<void> {
  const settings = await getSettings();
  applyTheme(settings.theme);

  const tokens = await getTokens();
  if (tokens) {
    showDashboard();
  } else {
    showLogin();
  }
}

void init();
