// Quit: stop the server from the page, asking first when work would be cut short.

import { get, post } from "./api.js";
import { h, replace } from "./dom.js";
import { t } from "./i18n.js";
import { unwatch } from "./jobs.js";
import { attempt } from "./notice.js";

export function quitButton(button, view) {
  button.addEventListener("click", async () => {
    const jobs = await attempt(() => get("/jobs"));
    if (!jobs) return;
    const running = jobs.find((job) => !job.finished_at);
    if (!running) return quit();
    // Back to the screen the address names.
    const back = () => dispatchEvent(new HashChangeEvent("hashchange"));
    replace(
      view,
      h("h1", {}, t("quit.title")),
      h(
        "section",
        { class: "card" },
        h("p", {}, t("quit.busy", { job: t(`job.kind.${running.kind}`) })),
        h("p", { class: "muted" }, t("quit.resume")),
        h(
          "div",
          { class: "row" },
          h("button", { class: "primary", onclick: quit }, t("quit.anyway")),
          h("button", { onclick: back }, t("common.cancel")),
        ),
      ),
    );
  });
}

async function quit() {
  if (!(await attempt(() => post("/quit")))) return;
  unwatch();
  document.title = t("quit.stopped");
  document.body.replaceChildren(
    h("main", {}, h("h1", {}, t("quit.stopped")), h("p", {}, t("quit.close_tab"))),
  );
}
