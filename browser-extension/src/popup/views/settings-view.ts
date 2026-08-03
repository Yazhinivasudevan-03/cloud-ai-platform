import { getSettings, setSettings } from "../../shared/storage";
import type { ExtensionSettings } from "../../shared/types";
import { applyTheme } from "../theme";

interface SettingsCallbacks {
  onBack: () => void;
  onLogout: () => void;
}

export async function renderSettings(container: HTMLElement, callbacks: SettingsCallbacks): Promise<void> {
  const settings = await getSettings();

  container.innerHTML = `
    <div class="topbar">
      <h1>Settings</h1>
      <button class="icon-btn" id="back-btn" title="Back">&larr;</button>
    </div>
    <div class="content">
      <form id="settings-form">
        <div class="settings-row">
          <label for="s-notifications" style="flex-direction:row;align-items:center;gap:6px">Enable notifications</label>
          <input type="checkbox" id="s-notifications" ${settings.notificationsEnabled ? "checked" : ""} />
        </div>
        <div class="settings-row">
          <label for="s-sound" style="flex-direction:row;align-items:center;gap:6px">Notification sound</label>
          <input type="checkbox" id="s-sound" ${settings.notificationSound ? "checked" : ""} />
        </div>
        <label>Refresh interval (minutes, minimum 1)
          <input type="number" id="s-interval" min="1" max="60" value="${settings.refreshIntervalMinutes}" required />
        </label>
        <label>Theme
          <select id="s-theme">
            <option value="system" ${settings.theme === "system" ? "selected" : ""}>Match system</option>
            <option value="light" ${settings.theme === "light" ? "selected" : ""}>Light</option>
            <option value="dark" ${settings.theme === "dark" ? "selected" : ""}>Dark</option>
          </select>
        </label>
        <label>Backend API URL
          <input type="url" id="s-backend" value="${settings.backendBaseUrl}" required />
        </label>
        <label>Web app URL
          <input type="url" id="s-webapp" value="${settings.webAppBaseUrl}" required />
        </label>
        <div class="account-meta">
          Changing the Backend API URL to a non-localhost host also requires updating
          <code>host_permissions</code> in manifest.json and reloading the extension.
        </div>
        <button type="submit" class="primary">Save settings</button>
      </form>
      <button class="link" id="logout-btn" style="margin-top:12px">Log out</button>
    </div>
  `;

  container.querySelector<HTMLButtonElement>("#back-btn")!.addEventListener("click", callbacks.onBack);
  container.querySelector<HTMLButtonElement>("#logout-btn")!.addEventListener("click", callbacks.onLogout);

  container.querySelector<HTMLFormElement>("#settings-form")!.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      const updated: ExtensionSettings = {
        notificationsEnabled: container.querySelector<HTMLInputElement>("#s-notifications")!.checked,
        notificationSound: container.querySelector<HTMLInputElement>("#s-sound")!.checked,
        refreshIntervalMinutes: Math.max(
          1,
          Number(container.querySelector<HTMLInputElement>("#s-interval")!.value) || 1,
        ),
        theme: container.querySelector<HTMLSelectElement>("#s-theme")!.value as ExtensionSettings["theme"],
        backendBaseUrl: container.querySelector<HTMLInputElement>("#s-backend")!.value.replace(/\/+$/, ""),
        webAppBaseUrl: container.querySelector<HTMLInputElement>("#s-webapp")!.value.replace(/\/+$/, ""),
      };
      await setSettings(updated);
      applyTheme(updated.theme);
      chrome.runtime.sendMessage({ type: "APPLY_SETTINGS" });
      callbacks.onBack();
    })();
  });
}
