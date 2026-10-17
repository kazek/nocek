// One recording: see it, hear it, and what each method made of it.

import { get } from "../api.js";
import { h, replace } from "../dom.js";
import { formatDate, formatDateTime, formatNumber, lang, t } from "../i18n.js";
import { taxaLabel } from "../names.js";
import { go } from "../router.js";
import { spectrogram } from "../spectrogram.js";

const SLOWDOWN = 10;

export async function recording(view, id) {
  const [rec, sites, devices] = await Promise.all([get(`/recordings/${id}`), get("/sites"), get("/devices")]);
  const result = rec.result;
  const sources = result?.batdetect ?? [];
  const neighbours = await nearby(rec);
  const site = sites.find((s) => s.id === rec.site_id);
  const device = devices.find((d) => d.id === rec.device_id);

  const audio = h("audio", { controls: true, preload: "none", src: `/api/recordings/${id}/audio?slowdown=${SLOWDOWN}` });
  const whole = h("button", { hidden: true }, t("recording.whole"));
  const picture = spectrogram(id, rec.duration_s ?? 0, sources, {
    onZoom: (start, end) => {
      whole.hidden = start <= 0 && end >= rec.duration_s;
      audio.currentTime = start * SLOWDOWN;
    },
  });
  whole.onclick = () => picture.zoom(0, rec.duration_s);

  // The cursor follows the sound; playback stays inside the stretch on screen.
  const follow = () => {
    const [start, end] = picture.range();
    const at = audio.currentTime / SLOWDOWN;
    if (at >= end) {
      audio.pause();
      audio.currentTime = start * SLOWDOWN;
    }
    picture.cursor(audio.currentTime / SLOWDOWN);
    if (!audio.paused) requestAnimationFrame(follow);
  };
  audio.addEventListener("play", () => {
    const [start, end] = picture.range();
    const at = audio.currentTime / SLOWDOWN;
    if (at < start || at >= end) audio.currentTime = start * SLOWDOWN;
    requestAnimationFrame(follow);
  });
  audio.addEventListener("pause", () => picture.cursor(audio.currentTime / SLOWDOWN));

  replace(
    view,
    h(
      "div",
      { class: "row" },
      h("a", { href: `#/nights/${rec.night}` }, `← ${formatDate(rec.night)}`),
      h("span", { class: "spacer" }),
      h("button", { disabled: !neighbours.previous, onclick: () => go(`/recording/${neighbours.previous}`) }, `← ${t("recording.previous")}`),
      h("button", { disabled: !neighbours.next, onclick: () => go(`/recording/${neighbours.next}`) }, `${t("recording.next")} →`),
    ),
    h("h1", {}, rec.recorded_at ? formatDateTime(rec.recorded_at) : rec.file_name),
    h(
      "p",
      { class: "muted" },
      h("span", { class: "path" }, rec.file_name),
      site ? ` · ${t("recording.site")}: ${site.name}` : "",
      device ? ` · ${t("recording.device")}: ${device.label ?? device.uid}` : "",
    ),
    h("div", { class: "card" }, picture.element, h("div", { class: "row" }, audio, whole, h("span", { class: "muted" }, t("recording.zoom_hint")))),
    h("p", { class: "muted" }, t("recording.slowed", { n: SLOWDOWN })),
    verdict(result),
  );

  // Space plays and pauses; the arrows step through the night.
  const keys = (event) => {
    if (!document.body.contains(view.firstChild) || event.target.closest("input, select, textarea, button, audio")) return;
    if (event.key === " ") {
      event.preventDefault();
      if (audio.paused) audio.play();
      else audio.pause();
    } else if (event.key === "ArrowLeft" && neighbours.previous) go(`/recording/${neighbours.previous}`);
    else if (event.key === "ArrowRight" && neighbours.next) go(`/recording/${neighbours.next}`);
  };
  document.addEventListener("keydown", keys);
  addEventListener("hashchange", () => document.removeEventListener("keydown", keys), { once: true });
}

async function nearby(rec) {
  if (!rec.night) return {};
  const page = await get(`/recordings?first_night=${rec.night}&last_night=${rec.night}&limit=1000`);
  const at = page.rows.findIndex((r) => r.id === rec.id);
  return { previous: page.rows[at - 1]?.id, next: page.rows[at + 1]?.id };
}

function verdict(result) {
  if (!result) return h("p", {}, t("recording.not_analysed"));
  const percent = new Intl.NumberFormat(lang(), { style: "percent" });
  const sources = result.verdict ?? [];

  const animals =
    sources.length === 0
      ? h("p", {}, t("recording.no_calls"))
      : h(
          "ol",
          { class: "animals" },
          sources.map((v, i) =>
            h(
              "li",
              { class: "card" },
              h("span", { class: "number" }, String(i + 1)),
              h(
                "div",
                {},
                v.taxa ? h("div", { class: "name" }, taxaLabel(v.taxa)) : h("div", { class: "name muted" }, t("recording.withheld")),
                v.reasons.map((r) => h("div", { class: "warn" }, t(`abstention.${r}`))),
                v.notes.map((n) => h("div", { class: "muted" }, t(`note.${n}`))),
                v.taxa
                  ? h(
                      "div",
                      { class: "muted" },
                      v.agreement.named > 1
                        ? t("recording.agreement", { agreeing: v.agreement.agreeing, named: v.agreement.named, count: v.agreement.named })
                        : t("recording.only_network"),
                    )
                  : null,
                details(v, result.batdetect[v.source], percent),
              ),
            ),
          ),
        );

  return h(
    "section",
    {},
    h("h2", {}, t("recording.verdict")),
    animals,
    recordingDetails(result, percent),
  );
}

function opinionText(opinion, percent) {
  if (!opinion) return t("recording.no_opinion");
  const leader = opinion.ranking[0];
  if (!leader) return t("recording.no_opinion");
  return [taxaLabel(leader.taxa), ` ${percent.format(leader.score)}`];
}

function details(v, source, percent) {
  return h(
    "details",
    {},
    h("summary", {}, t("recording.details")),
    h(
      "dl",
      { class: "facts" },
      h("dt", {}, t("recording.method.batdetect2")),
      h("dd", {}, opinionText(source.opinion, percent)),
      h("dt", {}, t("recording.model_class")),
      h("dd", { class: "scientific" }, source.model_class),
      h("dt", {}, t("recording.calls")),
      h("dd", {}, formatNumber(source.calls.length)),
      h("dt", {}, t("recording.votes")),
      h("dd", {}, percent.format(source.agreement)),
      h("dt", {}, t("recording.method.key")),
      h("dd", {}, opinionText(v.key, percent)),
      h("dt", {}, t("recording.method.battybirdnet")),
      h("dd", {}, opinionText(v.battybird, percent)),
    ),
  );
}

function recordingDetails(result, percent) {
  const group = result.detection?.dominant;
  const rows = [];
  if (result.detection) rows.push([t("recording.pulses"), formatNumber(result.detection.pulses.length)]);
  if (group) {
    rows.push([t("recording.end_khz"), t("recording.khz", { n: formatNumber(Number(group.end_khz.toFixed(1))) })]);
    rows.push([t("recording.duration"), t("recording.ms", { n: formatNumber(Number(group.duration_ms.toFixed(1))) })]);
    if (group.interval_ms !== null) {
      rows.push([t("recording.interval"), t("recording.ms", { n: formatNumber(Math.round(group.interval_ms)) })]);
    }
  }
  const sounds = result.battybird?.not_a_bat ?? [];
  const skipped = Object.entries(result.skipped);
  return h(
    "details",
    { class: "card" },
    h("summary", {}, t("recording.measured")),
    h("dl", { class: "facts" }, rows.flatMap(([label, value]) => [h("dt", {}, label), h("dd", {}, value)])),
    sounds.length
      ? h(
          "p",
          {},
          `${t("recording.also_heard")}: `,
          sounds.map((s) => `${t(`recording.sound.${s.label}`)} (${percent.format(s.score)})`).join(", "),
        )
      : null,
    skipped.length
      ? h(
          "p",
          { class: "muted" },
          `${t("recording.not_run")}: `,
          skipped.map(([pass, why]) => `${t(`recording.method.${pass}`)} — ${t(`recording.skipped.${why}`)}`).join("; "),
        )
      : null,
    result.failures.length
      ? h("p", { class: "warn" }, `${t("recording.failed")}: `, result.failures.map((f) => f.stage).join(", "))
      : null,
    h("p", { class: "muted" }, Object.entries(result.versions).map(([k, v]) => `${k} ${v}`).join(" · ")),
  );
}
