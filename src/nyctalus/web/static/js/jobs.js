// The strip under the header: what is running in the background, and how far it got.

import { get, post } from "./api.js";
import { h, replace } from "./dom.js";
import { t, formatNumber } from "./i18n.js";
import { attempt } from "./notice.js";

const listeners = new Set();
let timer = null;
let poll = async () => {};
let stopped = false;

// Be told about every job that finishes, e.g. to refresh what is on screen.
export function onFinished(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
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

function draw(strip, jobs) {
  const running = jobs.find((job) => job.status === "running") ?? jobs.find((job) => !job.finished_at);
  if (!running) {
    const last = jobs[0];
    replace(
      strip,
      last
        ? h(
            "span",
            { class: last.status === "failed" ? "failed" : "" },
            `${t(`job.kind.${last.kind}`)}: ${t(`job.status.${last.status}`)}`,
            last.error ? ` — ${t(`error.${last.error}`)}` : "",
          )
        : t("job.idle"),
    );
    return;
  }
  const label = running.phase ? t(`job.phase.${running.phase}`) : t(`job.kind.${running.kind}`);
  const known = running.total > 0;
  replace(
    strip,
    h("strong", {}, label),
    h("progress", known ? { max: running.total, value: running.done } : {}),
    known
      ? t("job.progress", { done: formatNumber(running.done), total: formatNumber(running.total) })
      : t(`job.status.${running.status}`),
    running.item ? h("span", { class: "path" }, running.item) : null,
    h(
      "button",
      { onclick: () => attempt(() => post(`/jobs/${running.id}/cancel`)) },
      t("job.cancel"),
    ),
  );
}

// Start a job and resolve when it has finished.
export async function run(path, body) {
  const job = await post(path, body);
  return new Promise((resolve) => {
    const stop = onFinished((finished) => {
      if (finished.id === job.id) {
        stop();
        resolve(finished);
      }
    });
    poll();
  });
}
