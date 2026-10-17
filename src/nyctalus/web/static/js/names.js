// Bats by name: the local name first, the scientific one beside it.

import { h } from "./dom.js";
import { has, t } from "./i18n.js";

export function localName(name) {
  const key = name.includes(" ") ? `species.${name}` : `genus.${name}`;
  return has(key) ? t(key) : scientificName(name);
}

export function scientificName(name) {
  return name.includes(" ") ? name : `${name} sp.`;
}

// One animal that may stand for several taxa: "Kuhl's / Nathusius' pipistrelle".
export function taxaLabel(names) {
  return h(
    "span",
    { class: "taxon" },
    h("span", { class: "local" }, names.map(localName).join(" / ")),
    " ",
    h("i", { class: "scientific" }, names.map(scientificName).join(" / ")),
  );
}
