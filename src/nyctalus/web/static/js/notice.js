// A message at the top of the page, for errors the user should see.

import { t, has } from "./i18n.js";

const box = () => document.getElementById("notice");

export function showError(error) {
  const key = `error.${error.code ?? "failed"}`;
  box().textContent = has(key) ? t(key) : t("error.failed");
  box().hidden = false;
  console.error(error);
}

export function clearNotice() {
  box().hidden = true;
}

// Run an action, showing its error instead of throwing it.
export async function attempt(action) {
  clearNotice();
  try {
    return await action();
  } catch (error) {
    showError(error);
    return undefined;
  }
}
