// A Web Awesome dialog over the page, its content drawn by render(body), removed when
// it closes. onClose runs then, so the page can show what changed.

import { h } from "./dom.js";
import { showError } from "./notice.js";

export function openDialog(label, render, { onClose = () => {}, wide = false } = {}) {
  const body = h("div", { class: "dialog-body" });
  // A menu item's "…" says a dialog follows; the dialog's own title does without it.
  const title = label.replace(/…$/, "");
  const dialog = h("wa-dialog", { label: title, class: wide ? "wide" : "", "light-dismiss": true }, body);
  // The page learns of the closing at once; the dialog goes once its animation has run.
  // (Events from a dropdown inside closing are not the dialog's.)
  dialog.addEventListener("wa-hide", (event) => event.target === dialog && onClose());
  dialog.addEventListener("wa-after-hide", (event) => event.target === dialog && dialog.remove());
  document.body.append(dialog);
  Promise.resolve(render(body)).catch(showError);
  requestAnimationFrame(() => (dialog.open = true));
  return dialog;
}
