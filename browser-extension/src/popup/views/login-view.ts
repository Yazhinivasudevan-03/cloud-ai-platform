import { AuthError, login } from "../../shared/auth";

export function renderLogin(container: HTMLElement, onSuccess: () => void): void {
  container.innerHTML = `
    <div class="login-shell">
      <h1>Cloud AI Platform Monitor</h1>
      <p class="subtitle">Sign in with your existing platform account.</p>
      <div class="error" id="login-error" style="display:none"></div>
      <form id="login-form">
        <label>Username or email
          <input type="text" id="login-username" autocomplete="username" required />
        </label>
        <label>Password
          <input type="password" id="login-password" autocomplete="current-password" required />
        </label>
        <div class="checkbox-row">
          <input type="checkbox" id="login-remember" />
          <label for="login-remember" style="margin:0">Remember me</label>
        </div>
        <button type="submit" class="primary" id="login-submit">Log in</button>
      </form>
    </div>
  `;

  const form = container.querySelector<HTMLFormElement>("#login-form")!;
  const errorBox = container.querySelector<HTMLDivElement>("#login-error")!;
  const submitBtn = container.querySelector<HTMLButtonElement>("#login-submit")!;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      const username = (container.querySelector<HTMLInputElement>("#login-username")!).value.trim();
      const password = (container.querySelector<HTMLInputElement>("#login-password")!).value;
      const rememberMe = (container.querySelector<HTMLInputElement>("#login-remember")!).checked;

      errorBox.style.display = "none";
      submitBtn.disabled = true;
      submitBtn.textContent = "Signing in...";

      try {
        await login(username, password, rememberMe);
        onSuccess();
      } catch (err) {
        errorBox.textContent = err instanceof AuthError ? err.message : "Could not reach the backend.";
        errorBox.style.display = "block";
        submitBtn.disabled = false;
        submitBtn.textContent = "Log in";
      }
    })();
  });
}
