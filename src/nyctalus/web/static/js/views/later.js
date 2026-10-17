// A screen that is not built yet.

import { h, replace } from "../dom.js";
import { t } from "../i18n.js";

export function later(titleKey) {
  return (view) =>
    replace(view, h("h1", {}, t(titleKey)), h("p", { class: "muted" }, t("common.later")));
}
