// The main page, top to bottom: bring recordings in, pick a site, pick a night, see
// the whole night at a glance, look closely at one recording. What is picked is kept
// in the address (#/?site=1&night=2026-09-03&recording=5; site=none for recordings no
// site was found for), so a reload or a bookmark comes back to it.

import { get } from "../api.js";
import { assignHues } from "../bat-colours.js";
import { calendar } from "../calendar.js";
import { openDialog } from "../dialog.js";
import { h, replace } from "../dom.js";
import { formatDate, formatNumber, t } from "../i18n.js";
import { onFinished, onUpdate } from "../jobs.js";
import { numberName } from "../names.js";
import { nightBar } from "../nightbar.js";
import { devices as devicesPanel } from "./devices.js";
import { importPanel } from "./import.js";
import { recordingPanel } from "./recording.js";
import { sites as sitesPanel } from "./sites.js";

const PAGE = 1000; // recordings fetched at a time; a night rarely holds more
const NONE = "none"; // the tab of recordings without a site
const ROWS = 6; // sites in a column before another begins
const REFRESH_MS = 15000; // how often the page catches up while recordings are processed

export async function home(view, query) {
  const site = query.get("site");
  const state = {
    site: site === NONE ? NONE : site ? Number(site) : null,
    night: query.get("night"),
    recording: query.get("recording") ? Number(query.get("recording")) : null,
  };
  const sections = {
    sites: h("section", { class: "card site-list" }),
    nights: h("section", { class: "card nights" }),
    night: h("section", { class: "card night" }),
    recording: h("section"),
  };
  // The sites beside the calendar; the night, then the recording, the whole width under them.
  replace(view, importPanel(), h("div", { class: "overview" }, sections.sites, sections.nights), sections.night, sections.recording);

  let sites = [];
  let devices = [];
  let withoutSite = 0;
  let hues = new Map();
  let rows = [];
  let bar = null;
  let panel = null;
  let autoPicked = false; // whether the recording shown was chosen for the user
  let shown = null; // what the recording panel was drawn from
  let sameNight = null; // the night the bar shows
  // Each answer is used only if nothing newer was asked for meanwhile.
  const latest = { site: 0, night: 0, recording: 0 };

  const remember = () => {
    const kept = Object.entries(state).filter(([, value]) => value !== null);
    history.replaceState(null, "", `#/?${new URLSearchParams(kept)}`);
  };
  // The chosen site as the API's filter.
  const where = () => (state.site === NONE ? "without_site=true" : `site_id=${state.site}`);

  const loadSites = async () => {
    let numbers;
    [sites, devices, numbers] = await Promise.all([get("/sites"), get("/devices"), get("/numbers")]);
    sites = sites.filter((s) => s.recordings > 0);
    withoutSite = numbers.without_site;
    const known = [...sites.map((s) => s.id), ...(withoutSite ? [NONE] : [])];
    if (!known.includes(state.site)) {
      // The one recorded at most recently.
      const recent = [...sites].sort((a, b) => (b.last_night ?? "").localeCompare(a.last_night ?? ""))[0];
      state.site = recent?.id ?? (withoutSite ? NONE : null);
    }
  };

  // A site's numbers as its recordings' names spell them; the recorder too, if there
  // is more than one.
  const numbersOf = (site) =>
    site.numbers
      .map((n) => {
        const device = devices.find((d) => d.id === n.device_id);
        const recorder = devices.length > 1 && device ? `${device.label ?? device.uid} ` : "";
        return recorder + numberName(n.device_number);
      })
      .join(", ");

  const drawSites = () => {
    if (sites.length === 0 && !withoutSite) {
      replace(sections.sites, h("p", { class: "muted" }, t("home.no_recordings")));
      return;
    }
    const tab = (id, label, detail) =>
      h(
        "wa-button",
        {
          size: "small",
          appearance: id === state.site ? "accent" : "outlined",
          variant: id === state.site ? "brand" : "neutral",
          "aria-pressed": id === state.site ? "true" : "false",
          onclick: () => {
            if (id === state.site) return;
            state.site = id;
            state.night = null;
            state.recording = null;
            drawSites();
            showSite();
          },
        },
        h("wa-icon", { slot: "start", name: id === NONE ? "circle-alert" : "map-pin" }),
        label,
        detail ? h("span", { class: "site" }, ` · ${detail}`) : null,
      );
    const tabs = [
      ...sites.map((s) => tab(s.id, s.name, numbersOf(s) === s.name ? null : numbersOf(s))),
      ...(withoutSite ? [tab(NONE, t("home.without_site"), formatNumber(withoutSite))] : []),
    ];
    replace(
      sections.sites,
      h("div", { class: "section-head" }, h("h2", { title: t("home.site_hint") }, t("home.sites")), moreMenu()),
      // One under another, in as many columns as it takes to keep beside the calendar.
      h("div", { class: "sites", style: `--rows: ${Math.min(tabs.length, ROWS)}` }, tabs),
    );
  };

  // Sites and their numbers, the recorders, and the data as files.
  const moreMenu = () => {
    const refresh = async () => {
      await loadSites();
      drawSites();
      await showSite();
    };
    const csv = (name) => `/api/${name}.csv?${where()}`;
    const menu = h(
      "wa-dropdown",
      { placement: "bottom-end" },
      h("wa-button", { slot: "trigger", size: "small", appearance: "plain" }, h("wa-icon", { name: "ellipsis", label: t("home.more") })),
      h("wa-dropdown-item", { value: "sites" }, h("wa-icon", { slot: "icon", name: "map-pin" }), t("home.menu.sites")),
      h("wa-dropdown-item", { value: "devices" }, h("wa-icon", { slot: "icon", name: "radio" }), t("home.menu.devices")),
      h("wa-divider"),
      h("wa-dropdown-item", { value: "species-csv" }, h("wa-icon", { slot: "icon", name: "download" }), t("home.menu.species_csv")),
      h("wa-dropdown-item", { value: "recordings-csv" }, h("wa-icon", { slot: "icon", name: "download" }), t("home.menu.recordings_csv")),
    );
    menu.addEventListener("wa-select", (event) => {
      const choice = event.detail.item.value;
      if (choice === "sites") openDialog(t("home.menu.sites"), sitesPanel, { onClose: refresh, wide: true });
      else if (choice === "devices") openDialog(t("home.menu.devices"), devicesPanel, { onClose: refresh, wide: true });
      else location.href = csv(choice === "species-csv" ? "species" : "recordings");
    });
    return menu;
  };

  const showSite = async () => {
    const ticket = ++latest.site;
    if (state.site === null) {
      Object.values(sections).slice(1).forEach((s) => replace(s));
      sections.nights.hidden = sections.night.hidden = true;
      return;
    }
    const [nights, totals] = await Promise.all([get(`/nights?${where()}`), get(`/totals?${where()}`)]);
    if (ticket !== latest.site) return;
    hues = assignHues(totals.species);
    if (!nights.some((n) => n.night === state.night)) state.night = nights.at(-1)?.night ?? null;
    sections.nights.hidden = false;
    replace(
      sections.nights,
      h(
        "div",
        { class: "section-head" },
        h("h2", {}, t("home.nights")),
        h(
          "span",
          { class: "muted" },
          t("home.season", {
            recordings: t("count.recordings", { n: formatNumber(totals.recordings), count: totals.recordings }),
            nights: t("count.nights", { n: formatNumber(totals.nights), count: totals.nights }),
            bats: t("home.named_bats", { n: formatNumber(totals.species.length), count: totals.species.length }),
          }),
        ),
      ),
      calendar(nights, {
        selected: state.night,
        onSelect: (night) => {
          state.night = night;
          state.recording = null;
          showNight();
        },
      }),
    );
    await showNight();
  };

  const showNight = async () => {
    const ticket = ++latest.night;
    if (state.night === null) {
      sections.night.hidden = true;
      replace(sections.recording);
      return;
    }
    const found = await recordingsOf(where(), state.night);
    if (ticket !== latest.night) return;
    rows = found;
    const sun =
      state.site === NONE
        ? { sunset: null, sunrise: null }
        : await get(`/sun?night=${state.night}&site_id=${state.site}`);
    if (ticket !== latest.night) return;
    // The night opens on its first recording with a named bat. A recording picked that
    // way, before the night was analysed, gives way to such a one once there is one;
    // one the user picked stays.
    const current = rows.find((r) => r.id === state.recording);
    if (!current || (autoPicked && !current.named.length)) {
      state.recording = (rows.find((r) => r.named.length) ?? rows[0])?.id ?? null;
      autoPicked = true;
    }
    // Drawn again, the same night keeps its place on a widened bar.
    const scroll = bar && sameNight === state.night ? bar.scrollLeft() : null;
    sameNight = state.night;
    bar = nightBar(rows, sun, hues, { selected: state.recording, onSelect: pick, scroll });
    sections.night.hidden = false;
    replace(
      sections.night,
      h(
        "div",
        { class: "section-head" },
        h("h2", {}, t("home.night_of", { date: formatDate(state.night) })),
        h(
          "span",
          { class: "muted" },
          t("count.recordings", { n: formatNumber(rows.length), count: rows.length }),
          sun.sunset || state.site === NONE ? "" : ` · ${t("home.no_sun")}`,
        ),
      ),
      bar.element,
    );
    await showRecording(state.recording);
  };

  // A recording the user chose, from the bar or by stepping.
  const pick = (id) => {
    autoPicked = false;
    return showRecording(id);
  };

  const showRecording = async (id) => {
    const at = rows.findIndex((r) => r.id === id);
    // Drawn again only when it changed: a refresh while it plays leaves it playing, and
    // the bar where it was scrolled to.
    const key = JSON.stringify([id, rows[at]?.analysed, rows[at]?.named, rows[at - 1]?.id, rows[at + 1]?.id]);
    if (panel && id !== null && key === shown) return;
    const ticket = ++latest.recording;
    state.recording = id;
    remember();
    bar?.select(id);
    if (id === null) {
      replace(sections.recording);
      panel = null;
      shown = null;
      return;
    }
    const rec = await get(`/recordings/${id}`);
    const made = await recordingPanel(rec, {
      previous: rows[at - 1]?.id ?? null,
      next: rows[at + 1]?.id ?? null,
      onStep: pick,
    });
    if (ticket !== latest.recording) return;
    panel = made;
    shown = key;
    replace(sections.recording, panel.element);
  };

  // Space plays, the arrows step through the night. Gone once another screen shows.
  const keys = (event) => {
    if (!view.contains(sections.recording)) return;
    panel?.onKey(event);
  };
  document.addEventListener("keydown", keys);
  addEventListener("hashchange", () => document.removeEventListener("keydown", keys), { once: true });

  // New recordings or names: draw again, keeping what was picked; when a job is done,
  // and every REFRESH_MS while one runs, unless the pointer is on the night's bar.
  const KINDS = ["import", "analyse", "verdicts"];
  let refreshed = Date.now();
  let refreshing = false;
  const refresh = async () => {
    if (refreshing) return;
    refreshing = true;
    refreshed = Date.now();
    try {
      await loadSites();
      drawSites();
      await showSite();
    } finally {
      refreshing = false;
    }
  };
  const stopFinished = onFinished((job) => {
    if (!view.contains(sections.sites)) return stopFinished();
    if (KINDS.includes(job.kind) && job.status === "done") refresh();
  });
  const stopUpdates = onUpdate((jobs) => {
    if (!view.contains(sections.sites)) return stopUpdates();
    const busy = jobs.some((job) => !job.finished_at && KINDS.includes(job.kind));
    if (busy && Date.now() - refreshed > REFRESH_MS && !sections.night.matches(":hover")) refresh();
  });

  await loadSites();
  drawSites();
  await showSite();
}

// where: the API's filter for the site, e.g. "site_id=2".
async function recordingsOf(where, night) {
  const rows = [];
  for (let offset = 0; ; offset += PAGE) {
    const page = await get(`/recordings?${where}&first_night=${night}&last_night=${night}&limit=${PAGE}&offset=${offset}`);
    rows.push(...page.rows);
    if (rows.length >= page.total || page.rows.length === 0) return rows;
  }
}
