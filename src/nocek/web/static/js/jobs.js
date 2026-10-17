// The line under the header: what is running in the background, and how far it got.

import { get, post } from "./api.js";
import { h, replace } from "./dom.js";
import { t, formatNumber } from "./i18n.js";
import { attempt } from "./notice.js";

const listeners = new Set();
const watchers = new Set();
let timer = null;
let poll = async () => {};
let stopped = false;

// Be told about every job that finishes, e.g. to refresh what is on screen.
export function onFinished(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// Be told of every job, each time they are asked for, e.g. to show one's progress.
export function onUpdate(watcher) {
  watchers.add(watcher);
  return () => watchers.delete(watcher);
}

export function watch() {
  const strip = document.getElementById("jobs");
  const finished = new Set();
  let first = true;

  poll = async () => {
    clearTimeout(timer);
    let jobs = [];
    try {
      jobs = await get("/jobs");
    } catch {
      // The server may be restarting; try again shortly.
    }
    if (stopped) return;
    for (const job of jobs) {
      if (job.finished_at && !finished.has(job.id)) {
        finished.add(job.id);
        if (!first) listeners.forEach((listener) => listener(job));
      }
    }
    first = false;
    draw(strip, jobs);
    watchers.forEach((watcher) => watcher(jobs));
    const busy = jobs.some((job) => !job.finished_at);
    timer = setTimeout(poll, busy ? 1000 : 5000);
  };
  return poll;
}

// Stop asking: the server is going away.
export function unwatch() {
  stopped = true;
  clearTimeout(timer);
}

// The line under the header: there while something runs, or when the last job failed;
// otherwise it takes no room at all.
function draw(strip, jobs) {
  const running = jobs.find((job) => job.status === "running") ?? jobs.find((job) => !job.finished_at);
  if (!running) {
    const last = jobs[0];
    strip.hidden = last?.status !== "failed";
    if (!strip.hidden) {
      replace(
        strip,
        h("wa-icon", { name: "circle-alert" }),
        h("span", { class: "failed" }, `${t(`job.kind.${last.kind}`)}: ${t(`job.status.${last.status}`)}`, last.error ? ` — ${t(`error.${last.error}`)}` : ""),
      );
    }
    return;
  }
  strip.hidden = false;
  replace(
    strip,
    progressOf(running),
    h(
      "wa-button",
      { size: "small", appearance: "plain", onclick: () => attempt(() => post(`/jobs/${running.id}/cancel`)) },
      t("job.cancel"),
    ),
  );
}

// How far a job got: what it is doing, a bar, how many of how many, and the file at hand.
// Each part keeps its size from one report to the next, so nothing around it moves.
export function progressOf(job) {
  const known = job.total > 0;
  return [
    h("strong", {}, job.phase ? t(`job.phase.${job.phase}`) : t(`job.kind.${job.kind}`)),
    h("progress", known ? { max: job.total, value: job.done } : {}),
    h(
      "span",
      { class: "count" },
      known ? t("job.progress", { done: formatNumber(job.done), total: formatNumber(job.total) }) : t(`job.status.${job.status}`),
    ),
    h("span", { class: "path" }, job.item ?? ""),
  ];
}

// Start a job and resolve when it has finished; onProgress(job) hears how it goes.
export async function run(path, body, onProgress = () => {}) {
  const job = await post(path, body);
  return new Promise((resolve) => {
    const unwatch = onUpdate((jobs) => {
      const now = jobs.find((j) => j.id === job.id);
      if (now && !now.finished_at) onProgress(now);
    });
    const stop = onFinished((finished) => {
      if (finished.id === job.id) {
        stop();
        unwatch();
        resolve(finished);
      }
    });
    poll();
  });
}
