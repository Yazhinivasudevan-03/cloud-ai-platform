# Browser Extension - Installation Guide

The extension is unpacked/side-loaded (not published to a web store) - this is the normal,
supported way to run a Manifest V3 extension during development or for internal use. It works
identically on any Chromium-based browser: **Chrome, Microsoft Edge, Brave, and Opera** all load
unpacked extensions the same way, since they all implement the same `chrome.*` extension APIs. Steps
below are written for Chrome and Edge explicitly, per the deliverables list; Brave/Opera follow the
identical flow at their own `brave://extensions` / `opera://extensions` pages.

## 1. Build the extension

```bash
cd browser-extension
npm install
npm run build
```

This produces `browser-extension/dist/` - a complete, loadable unpacked extension (`manifest.json`,
the popup, the background service worker, and icons).

## 2. Make sure the backend is reachable

By default the extension expects the backend at `http://localhost:8000/api/v1` and the web app at
`http://localhost:3000` (the same defaults `docker compose up` already uses). Both can be changed later
from the extension's own Settings screen - but if you point the Backend API URL at anything other than
`localhost:8000`, you must also add that host to `host_permissions` in `browser-extension/manifest.json`
and reload the extension (a real Manifest V3 requirement, not optional).

## 3. Load it - Google Chrome

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked**.
4. Select the `browser-extension/dist` folder.
5. The extension appears in your toolbar - pin it for quick access (puzzle-piece icon → pin).

## 4. Load it - Microsoft Edge

1. Open `edge://extensions`.
2. Turn on **Developer mode** (left sidebar toggle).
3. Click **Load unpacked**.
4. Select the `browser-extension/dist` folder.
5. Pin it from the extensions toolbar menu if you want it always visible.

## 5. Brave / Opera (same flow)

- Brave: `brave://extensions` → Developer mode → Load unpacked → select `dist`.
- Opera: `opera://extensions` → Developer mode → Load unpacked → select `dist`.

## 6. First use

1. Click the extension icon - you'll see the login screen.
2. Sign in with your existing platform account (the same one you use on the web app).
3. The popup shows your connected cloud accounts, active/critical alerts, AI recommendations,
   resource usage, and this month's cloud cost - all fetched fresh from the same backend the web app
   uses.
4. Open **Settings** (gear icon) to adjust the refresh interval, notification sound, theme, or log out.

## Rebuilding after a code change

Re-run `npm run build`, then click the reload icon on the extension's card in
`chrome://extensions` / `edge://extensions` - unpacked extensions don't auto-reload.

## Uninstalling

Remove it from `chrome://extensions` / `edge://extensions` like any other extension. This only removes
the extension itself - your account and data on the platform are untouched.
