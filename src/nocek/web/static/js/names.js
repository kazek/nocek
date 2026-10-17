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

// A recorder's mode as the recorder wrote it, translated when it is a known one.
export function recorderMode(mode) {
  return has(`recorder_mode.${mode}`) ? t(`recorder_mode.${mode}`) : mode;
}

// An issue with a recorder's settings, in words.
export function configIssue(issue) {
  const details = issue.issue === "not-bat-mode" ? issue.details.map(recorderMode) : issue.details;
  return t(`config_issue.${issue.issue}`, details);
}

export function regionName(profile) {
  return profile && has(`region_name.${profile.id}`) ? t(`region_name.${profile.id}`) : (profile?.name ?? "");
}
