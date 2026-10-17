// Recorders: what to call them, and every setting they were given.

import { get, put } from "../api.js";
import { h, replace } from "../dom.js";
import { formatDateTime, formatNumber, t } from "../i18n.js";
import { configIssue, recorderMode } from "../names.js";
import { attempt } from "../notice.js";

export async function devices(view) {
  const list = await get("/devices");
  replace(
    view,
    list.length === 0 ? h("p", {}, t("devices_page.empty")) : list.map((device) => card(device, () => devices(view))),
  );
}

function card(device, redraw) {
  const label = h("input", { type: "text", value: device.label ?? "" });
  return h(
    "section",
    { class: "card" },
    h("h2", {}, device.label ?? device.uid),
    h("p", { class: "muted" }, t("devices_page.identifier", { kind: device.kind, uid: device.uid })),
    h(
      "form",
      {
        class: "row",
        onsubmit: async (event) => {
          event.preventDefault();
          if (await attempt(() => put(`/devices/${device.id}`, { label: label.value.trim() || null }))) redraw();
        },
      },
      h("label", {}, t("devices_page.label"), label),
      h("button", { type: "submit" }, t("devices_page.save")),
    ),
    device.configs.length
      ? h(
          "div",
          { class: "scroll" },
          h("h3", {}, t("devices_page.configs")),
          h(
            "table",
            {},
            h(
              "thead",
              {},
              h(
                "tr",
                {},
                ["written", "number", "schedule", "sensitivity", "position", "firmware", "issues"].map((k) =>
                  h("th", {}, t(`devices_page.${k}`)),
                ),
              ),
            ),
            h("tbody", {}, [...device.configs].reverse().map(configRow)),
          ),
        )
      : null,
  );
}

function configRow(config) {
  return h(
    "tr",
    {},
    h("td", { class: "date" }, formatDateTime(config.written_at)),
    h("td", { class: "number" }, formatNumber(config.number)),
    h(
      "td",
      {},
      config.schedules.map((s) => h("div", {}, t("devices_page.mode", { ...s, mode: recorderMode(s.mode) }))),
    ),
    h("td", { class: "number" }, config.trigger_sensitivity ?? t("devices_page.none")),
    h(
      "td",
      { class: "date" },
      config.location
        ? `${config.location.latitude.toFixed(4)}, ${config.location.longitude.toFixed(4)}`
        : t("devices_page.none"),
    ),
    h("td", {}, config.firmware ?? t("devices_page.none")),
    h(
      "td",
      {},
      config.issues.length
        ? config.issues.map((i) => h("div", { class: "warn" }, configIssue(i)))
        : t("devices_page.none"),
    ),
  );
}
