// One recording: see it, hear it, and what each method made of it.

import { get } from "../api.js";
import { openDialog } from "../dialog.js";
import { h, replace } from "../dom.js";
import { formatDateTime, formatNumber, lang, t } from "../i18n.js";
import { taxaLabel } from "../names.js";
import { spectrogram } from "../spectrogram.js";

const SLOWDOWN = 10;

// One recording, ready to be placed anywhere: the spectrogram, the player and the
// verdict. previous and next are the neighbouring recordings' ids, onStep(id) moves.
export async function recordingPanel(rec, { previous = null, next = null, onStep = () => {} } = {}) {
  const [sites, devices] = await Promise.all([get("/sites"), get("/devices")]);
  const id = rec.id;
  const result = rec.result;
  const sources = result?.batdetect ?? [];
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

  const step = (direction, other) =>
    h(
      "wa-button",
      { size: "small", appearance: "outlined", disabled: !other, onclick: () => other && onStep(other) },
      h("wa-icon", { slot: direction === "previous" ? "start" : "end", name: `chevron-${direction === "previous" ? "left" : "right"}` }),
      t(`recording.${direction}`),
    );

  const element = h(
    "section",
    { class: "recording" },
    h(
      "div",
      { class: "row recording-head" },
      step("previous", previous),
      h("strong", {}, rec.recorded_at ? formatDateTime(rec.recorded_at) : rec.file_name),
      step("next", next),
      h(
        "span",
        { class: "muted" },
        h("span", { class: "path" }, rec.file_name),
        site ? ` · ${t("recording.site")}: ${site.name}` : "",
        device ? ` · ${t("recording.device")}: ${device.label ?? device.uid}` : "",
      ),
    ),
    h(
      "div",
      { class: "card" },
      picture.element,
      h(
        "div",
        { class: "row" },
        audio,
        whole,
        h("span", { class: "muted" }, t("recording.slowed", { n: SLOWDOWN }), " ", t("recording.zoom_hint")),
      ),
      verdict(result),
    ),
  );

  // Space plays and pauses; the arrows step to the neighbouring recordings.
  const onKey = (event) => {
    if (event.target.closest("input, select, textarea, button, audio, wa-button, wa-dropdown")) return;
    if (event.key === " ") {
      event.preventDefault();
      if (audio.paused) audio.play();
      else audio.pause();
    } else if (event.key === "ArrowLeft" && previous) onStep(previous);
    else if (event.key === "ArrowRight" && next) onStep(next);
  };
  return { element, onKey };
}

// What was heard, one line per animal; how each method saw it, in a dialog.
function verdict(result) {
  if (!result) return h("p", { class: "muted" }, t("recording.not_analysed"));
  const percent = new Intl.NumberFormat(lang(), { style: "percent" });
  const sources = result.verdict ?? [];
  const more = h(
    "wa-button",
    {
      size: "small",
      appearance: "plain",
      onclick: () => openDialog(t("recording.details"), (body) => replace(body, explanation(result, percent)), { wide: true }),
    },
    h("wa-icon", { slot: "start", name: "info" }),
    t("recording.details"),
  );
  return h(
    "div",
    { class: "verdict" },
    h("span", { class: "label" }, t("recording.verdict")),
    sources.length === 0
      ? h("span", { class: "muted" }, t("recording.no_calls"))
      : h(
          "ol",
          { class: "animals" },
          sources.map((v, i) =>
            h(
              "li",
              {},
              h("span", { class: "number" }, String(i + 1)),
              v.taxa ? taxaLabel(v.taxa) : h("span", { class: "muted" }, t("recording.withheld")),
              v.taxa
                ? h(
                    "span",
                    { class: "muted" },
                    v.agreement.named > 1
                      ? t("recording.agreement", { agreeing: v.agreement.agreeing, named: v.agreement.named, count: v.agreement.named })
                      : t("recording.only_network"),
                  )
                : null,
              v.reasons.map((r) => h("span", { class: "warn" }, t(`abstention.${r}`))),
              v.notes.map((n) => h("span", { class: "muted" }, t(`note.${n}`))),
            ),
          ),
        ),
    more,
  );
}

// Everything behind the verdict: each animal as each method saw it, then what the
// detector measured, what else was heard, and what made the result.
function explanation(result, percent) {
  return [
    ...(result.verdict ?? []).map((v, i) =>
      h(
        "section",
        {},
        h("h3", {}, t("recording.animal", { n: i + 1 }), " · ", v.taxa ? taxaLabel(v.taxa) : t("recording.withheld")),
        facts(v, result.batdetect[v.source], percent),
      ),
    ),
    measurements(result, percent),
  ];
}

function opinionText(opinion, percent) {
  if (!opinion) return t("recording.no_opinion");
  const leader = opinion.ranking[0];
  if (!leader) return t("recording.no_opinion");
  return [taxaLabel(leader.taxa), ` ${percent.format(leader.score)}`];
}

function facts(v, source, percent) {
  return h(
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
  );
}

function measurements(result, percent) {
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
    "section",
    {},
    h("h3", {}, t("recording.measured")),
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
