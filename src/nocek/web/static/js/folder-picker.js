// Choosing a folder on this computer, through the server: browsers do not tell
// a page where a folder is. The server opens the system's own dialog, or, where
// there is none, lists folders for the page to show.

import { get, post } from "./api.js";
import { h, replace } from "./dom.js";
import { t, formatNumber } from "./i18n.js";
import { attempt } from "./notice.js";

// Resolves with the chosen folder's path, or null if the user cancelled.
export async function chooseFolder(container, { start = null, title = t("folders.title") } = {}) {
  try {
    return (await post("/folders/choose", { title, start })).path;
  } catch (error) {
    if (error.code !== "no-folder-dialog") throw error;
    return pickFolder(container, { start, title });
  }
}

// The page's own folder browser. Resolves with the chosen folder's path, or null if the user went back.
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
