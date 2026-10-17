// The interface's texts, in the language chosen for this browser.

import { get } from "./api.js";

let language = "en";
let texts = {};
let plurals = new Intl.PluralRules("en");

export async function load() {
  const { chosen } = await get("/locales");
  language = chosen;
  texts = await get(`/locales/${chosen}`);
  plurals = new Intl.PluralRules(chosen);
  document.documentElement.lang = chosen;
  for (const element of document.querySelectorAll("[data-text]")) {
    element.textContent = t(element.dataset.text);
  }
}

export function lang() {
  return language;
}

// t("job.status.done"), t("folders.recordings", { n: "1,234", count: 1234 }),
// t("config_issue.starts-after-sunset", ["18:05", "18:15"]). Plural forms are chosen by count, or by n
// when n is a plain number.
export function t(key, params = {}) {
  let value = key.split(".").reduce((node, part) => node?.[part], texts);
  if (value === undefined) {
    console.warn(`no text for ${key}`);
    return key;
  }
  if (typeof value === "object") {
    value = value[plurals.select(Number(params.count ?? params.n ?? 0))] ?? value.other;
  }
  return value.replace(/\{(\w+)\}/g, (match, name) => (name in params ? params[name] : match));
}

export function has(key) {
  return key.split(".").reduce((node, part) => node?.[part], texts) !== undefined;
}

export function formatNumber(n) {
  return new Intl.NumberFormat(language).format(n);
}

export function formatDate(isoDate) {
  return new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(
    new Date(`${isoDate}T12:00:00`),
  );
}

export function formatTime(isoDateTime) {
  return new Intl.DateTimeFormat(language, { timeStyle: "short", hourCycle: "h23" }).format(
    new Date(isoDateTime),
  );
}
