// Bringing recordings in from a card or a folder, and what was found there.

import { get, post } from "../api.js";
import { openDialog } from "../dialog.js";
import { h, replace } from "../dom.js";
import { chooseFolder } from "../folder-picker.js";
import { formatDateTime, formatNumber, t } from "../i18n.js";
import { progressOf, run } from "../jobs.js";
import { configIssue, numberName } from "../names.js";
import { attempt } from "../notice.js";

// Bringing recordings in, at the top of the main page: the button, the last import
// and the earlier ones in a line. Once a folder is chosen, the rest happens in a dialog.
export function importPanel() {
  const flow = h("div", { class: "import-flow" });
  const last = h("span", { class: "muted" });
  const button = h(
    "wa-button",
    { size: "small", variant: "brand" },
    h("wa-icon", { slot: "start", name: "folder-open" }),
    t("import.load"),
  );
  const ctx = { flow, last, button };
  button.onclick = () => askForFolder(ctx);
  const earlier = h(
    "wa-button",
    {
      size: "small",
      appearance: "plain",
      onclick: () => openDialog(t("import.history"), drawHistory, { wide: true, onClose: () => showLast(ctx.last) }),
    },
    h("wa-icon", { slot: "start", name: "ellipsis" }),
    t("import.history"),
  );
  showLast(last);
  return h("section", { class: "import-panel" }, h("div", { class: "row" }, button, last, earlier), flow);
}

// The last import, in a line.
async function showLast(last) {
  const [newest] = await get("/imports");
  last.textContent = newest
    ? t("import.last", {
        when: formatDateTime(newest.started_at),
        recordings: t("import.imported", { n: formatNumber(newest.copied), count: newest.copied }),
      })
    : "";
}

// The import's dialog has closed: let another begin.
function done(ctx) {
  replace(ctx.flow);
  ctx.button.disabled = false;
  ctx.dialog = null;
  showLast(ctx.last);
}

// The folder comes from the system's own dialog; everything after it, from settling the
// site to the report, happens in a dialog of ours, which "another folder" reuses.
async function askForFolder(ctx) {
  ctx.button.disabled = true; // while the system's dialog is open, and the import runs
  // Where there is no system dialog, the page's own folder browser shows here instead.
  const host = ctx.dialog ? ctx.body : ctx.flow;
  const folder = await attempt(() => chooseFolder(host, { title: t("import.choose_folder") }));
  replace(ctx.flow);
  if (!folder) {
    if (!ctx.dialog) done(ctx);
    return;
  }
  if (ctx.dialog) return confirm(ctx, folder);
  ctx.dialog = openDialog(
    t("import.load"),
    (body) => {
      ctx.body = body;
      return confirm(ctx, folder);
    },
    { wide: true, onClose: () => done(ctx) },
  );
}

async function confirm(ctx, folder) {
  const [sites, listing] = await Promise.all([get("/sites"), get(`/folders?path=${encodeURIComponent(folder)}&deep=true`)]);
  const site = h(
    "select",
    { "aria-label": t("import.site") },
    h("option", { value: "" }, t("import.site_auto")),
    sites.map((s) => h("option", { value: s.id }, s.name)),
  );
  const start = h("wa-button", { size: "small", variant: "brand" }, t("import.start"));
  start.onclick = async () => {
    // How the import goes, here as on the line under the header, which keeps it once
    // the dialog is closed.
    const progress = h("div", { class: "jobs-progress" });
    replace(ctx.body, h("p", { class: "muted" }, t("import.running")), progress);
    const job = await attempt(() =>
      run("/jobs/import", { folder, site_id: site.value ? Number(site.value) : null }, (now) =>
        replace(progress, progressOf(now)),
      ),
    );
    showLast(ctx.last);
    if (job?.status === "done") showReport(ctx, job.result);
    else confirm(ctx, folder); // failed or cancelled: the error says why; try again from here
  };
  const other = h("wa-button", { size: "small", appearance: "outlined", onclick: () => askForFolder(ctx) }, t("import.other_folder"));
  replace(
    ctx.body,
    h(
      "div",
      { class: "row confirm" },
      h("span", { class: "path" }, folder),
      h("span", { class: "muted" }, t("import.in_folder", { n: formatNumber(listing.recordings), count: listing.recordings })),
      h("label", {}, t("import.site"), site),
      start,
      other,
    ),
  );
}

async function showReport(ctx, report) {
  const sites = await get("/sites");
  const n = (count) => ({ n: formatNumber(count), count });
  const skipped = Object.entries(report.skipped);
  const homeless = report.notices.filter((notice) => notice.notice === "no-site");
  const others = report.notices.filter((notice) => notice.notice !== "no-site");

  replace(
    ctx.body,
    h(
      "div",
      { class: "report" },
      h("p", {}, report.copied ? t("import.copied", n(report.copied)) : t("import.nothing_new")),
      skipped.length
        ? h(
            "div",
            {},
            h("h3", {}, t("import.skipped")),
            h("ul", {}, skipped.map(([reason, count]) => h("li", {}, `${formatNumber(count)} — ${t(`import.skip.${reason}`)}`))),
          )
        : null,
      report.new_configs ? h("p", {}, t("import.new_configs", n(report.new_configs))) : null,
      report.issues.length
        ? h(
            "div",
            {},
            h("h3", {}, t("import.issues")),
            h(
              "ul",
              {},
              report.issues.map((issue) =>
                h("li", { class: "warn" }, `${formatDateTime(issue.written_at)}: ${configIssue(issue)}`),
              ),
            ),
          )
        : null,
      others.length || report.findings.length
        ? h(
            "div",
            {},
            h("h3", {}, t("import.found")),
            h(
              "ul",
              {},
              others.map((notice) => h("li", { class: "warn" }, t(`import.notice.${notice.notice}`))),
              findingsByProblem(report.findings),
            ),
          )
        : null,
      report.analysis_job
        ? h("p", { class: "muted" }, t("import.analysis_started"))
        : null,
    ),
    homeless.length
      ? h(
          "div",
          { class: "place-sites" },
          homeless.map((notice) => placeSite(report.import_id, notice, sites, () => showLast(ctx.last))),
        )
      : null,
  );
}

// Problems with files on the card, one line per kind, the files folded away.
function findingsByProblem(findings) {
  const groups = Map.groupBy(findings, (finding) => finding.problem);
  return [...groups].map(([problem, found]) =>
    h(
      "li",
      { class: "muted" },
      h(
        "details",
        {},
        h("summary", {}, `${t(`import.problem.${problem}`)} (${formatNumber(found.length)})`),
        h("ul", {}, found.map((finding) => h("li", { class: "path" }, finding.file))),
      ),
    ),
  );
}

// The recordings of an import that no site was found for, one number at a time: a new
// site for the number, named after it, or an existing one. Either way the number then
// stands for that site, and later imports with it need no asking.
function placeSite(importId, notice, sites, done) {
  const box = h("div", { class: "card" });
  const where = notice.location;
  const number = notice.device_number;
  const latitude = h("input", { type: "text", inputmode: "decimal", value: where ? where.latitude.toFixed(5) : "" });
  const longitude = h("input", { type: "text", inputmode: "decimal", value: where ? where.longitude.toFixed(5) : "" });
  const suggested =
    number !== null
      ? numberName(number)
      : where
        ? t("import.new_site_name", { latitude: where.latitude.toFixed(3), longitude: where.longitude.toFixed(3) })
        : "";
  const name = h("input", { type: "text", value: suggested });
  const existing = h("select", {}, sites.map((s) => h("option", { value: s.id }, s.name)));

  const assign = async (site) => {
    const result = await attempt(() => post(`/imports/${importId}/site`, { site_id: site.id, device_number: number }));
    if (!result) return;
    replace(box, h("p", { class: "ok" }, t("import.assigned", { n: formatNumber(result.assigned), count: result.assigned, site: site.name })));
    done();
  };

  const create = async () => {
    const site = await attempt(() =>
      post("/sites", {
        name: name.value.trim(),
        latitude: latitude.value ? Number(latitude.value) : null,
        longitude: longitude.value ? Number(longitude.value) : null,
      }),
    );
    if (site) await assign(site);
  };

  return replace(
    box,
    h("h2", {}, number !== null ? t("import.new_number", { number: numberName(number) }) : t("import.new_site")),
    h("p", { class: "muted" }, t("import.new_site_count", { n: formatNumber(notice.count), count: notice.count })),
    h("label", {}, t("import.name"), name),
    h("div", { class: "row" }, h("label", {}, t("import.latitude"), latitude), h("label", {}, t("import.longitude"), longitude)),
    where
      ? h(
          "p",
          {},
          h(
            "a",
            {
              href: `https://www.openstreetmap.org/?mlat=${where.latitude}&mlon=${where.longitude}#map=16/${where.latitude}/${where.longitude}`,
              target: "_blank",
              rel: "noopener noreferrer",
            },
            t("import.map"),
          ),
        )
      : null,
    h("button", { class: "primary", onclick: create }, t("import.create_site")),
    sites.length
      ? h(
          "div",
          { class: "row" },
          h("span", {}, t("import.or_existing")),
          existing,
          h("button", { onclick: () => assign(sites.find((s) => String(s.id) === existing.value)) }, t("import.assign")),
        )
      : null,
  );
}

// Every import so far, in the dialog; recordings an import left without a site can be
// given one here.
async function drawHistory(section) {
  const [imports, sites] = await Promise.all([get("/imports"), get("/sites")]);
  replace(
    section,
    imports.length === 0
      ? h("p", { class: "muted" }, t("import.history_empty"))
      : h(
          "ul",
          { class: "history" },
          imports.map((imp) =>
            h(
              "li",
              {},
              h("span", {}, formatDateTime(imp.started_at)),
              h("span", { class: "path" }, imp.source),
              h("span", {}, t("import.imported", { n: formatNumber(imp.copied), count: imp.copied })),
              imp.without_site
                ? h(
                    "span",
                    { class: "warn" },
                    t("import.without_site", { n: formatNumber(imp.without_site), count: imp.without_site }),
                    " ",
                    sites.length
                      ? h("button", { onclick: () => laterPlace(section, imp, sites) }, t("import.assign"))
                      : null,
                  )
                : null,
            ),
          ),
        ),
  );
}

function laterPlace(section, imp, sites) {
  const select = h("select", {}, sites.map((s) => h("option", { value: s.id }, s.name)));
  section.prepend(
    h(
      "div",
      { class: "card row" },
      h("span", {}, t("import.or_existing")),
      select,
      h(
        "button",
        {
          class: "primary",
          onclick: async () => {
            const site = sites.find((s) => String(s.id) === select.value);
            if (await attempt(() => post(`/imports/${imp.id}/site`, { site_id: site.id }))) drawHistory(section);
          },
        },
        t("import.assign"),
      ),
    ),
  );
}
