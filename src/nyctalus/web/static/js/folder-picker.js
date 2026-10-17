// Choosing a folder on this computer, through the server: browsers do not tell
// a page where a folder is, so the server lists folders for it.

import { get } from "./api.js";
import { h, replace } from "./dom.js";
import { t, formatNumber } from "./i18n.js";
import { attempt } from "./notice.js";

// Resolves with the chosen folder's path, or null if the user went back.
export function pickFolder(container, { start = null, title = t("folders.title") } = {}) {
  return new Promise((resolve) => {
    const list = h("ul", { class: "folders" });
    const where = h("p", { class: "path" });
    const choose = h("button", { class: "primary", disabled: true }, t("folders.choose"));
    const up = h("button", { disabled: true }, t("folders.up"));
    let current = null;

    const show = async (path) => {
      const listing = await attempt(() => get(path ? `/folders?path=${encodeURIComponent(path)}` : "/folders"));
      if (!listing) return;
      current = listing.path;
      where.textContent = listing.path ?? t("folders.places");
      choose.disabled = !listing.path;
      up.disabled = !listing.path;
      up.onclick = () => show(listing.parent);
      replace(
        list,
        listing.folders.length === 0 ? h("li", { class: "muted" }, t("folders.empty")) : null,
        listing.folders.map((folder) =>
          h(
            "li",
            {},
            h(
              "button",
              { onclick: () => show(folder.path) },
              h("span", {}, folder.name),
              folder.recordings
                ? h("span", { class: "muted" }, t("folders.recordings", { n: formatNumber(folder.recordings), count: folder.recordings }))
                : "",
            ),
          ),
        ),
      );
    };

    choose.onclick = () => resolve(current);
    replace(
      container,
      h(
        "div",
        { class: "card" },
        h("h2", {}, title),
        where,
        list,
        h("div", { class: "row" }, up, choose, h("button", { onclick: () => resolve(null) }, t("common.back"))),
      ),
    );
    show(start);
  });
}
