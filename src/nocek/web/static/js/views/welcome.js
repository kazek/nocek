// First run: a library to keep everything in, then the model files.

import { get, post } from "../api.js";
import { h, replace } from "../dom.js";
import { chooseFolder } from "../folder-picker.js";
import { t } from "../i18n.js";
import { run } from "../jobs.js";
import { attempt } from "../notice.js";
import { go } from "../router.js";

export async function welcome(view) {
  const [library, models] = await Promise.all([get("/library"), get("/models")]);
  const redraw = () => welcome(view);

  const libraryStep = library.open
    ? h("p", { class: "ok" }, t("welcome.library_ready", { path: library.path }))
    : h(
        "div",
        { class: "row" },
        h(
          "button",
          {
            class: "primary",
            onclick: () => use("/library/create", library.default_path),
          },
          t("welcome.create_here", { path: library.default_path }),
        ),
        h("button", { onclick: () => choose("/library/create", t("welcome.create_elsewhere")) }, t("welcome.create_elsewhere")),
        h("button", { onclick: () => choose("/library/open", t("welcome.open_existing")) }, t("welcome.open_existing")),
      );

  const modelsStep = models.present
    ? h("p", { class: "ok" }, t("welcome.models_ready"))
    : h(
        "div",
        {},
        h("p", {}, t("welcome.models_intro")),
        h(
          "button",
          {
            class: "primary",
            disabled: !library.open,
            onclick: async (event) => {
              event.target.disabled = true;
              const job = await attempt(() => run("/jobs/models"));
              if (job?.status === "done") redraw();
              else event.target.disabled = false;
            },
          },
          t("welcome.download"),
        ),
      );

  const ready = library.open && models.present;
  replace(
    view,
    h("h1", {}, t("welcome.title")),
    h("p", {}, t("welcome.intro")),
    h(
      "ol",
      { class: "steps" },
      h("li", { class: library.open ? "card done" : "card" }, h("h2", {}, t("welcome.library_step")), libraryStep),
      h(
        "li",
        { class: `card ${models.present ? "done" : library.open ? "" : "waiting"}` },
        h("h2", {}, t("welcome.models_step")),
        modelsStep,
      ),
      h(
        "li",
        { class: `card ${ready ? "" : "waiting"}` },
        h("h2", {}, t("welcome.ready_step")),
        h("p", {}, t("welcome.ready_text")),
        h("button", { class: "primary", disabled: !ready, onclick: () => go("/") }, t("welcome.start_import")),
      ),
    ),
  );

  async function use(endpoint, path) {
    if (await attempt(() => post(endpoint, { path }))) redraw();
  }

  async function choose(endpoint, title) {
    const path = await chooseFolder(view, { title });
    if (path) await use(endpoint, path);
    else redraw();
  }
}
