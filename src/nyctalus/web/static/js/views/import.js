// Bringing recordings in from a card or a folder, and what was found there.

import { get, post } from "../api.js";
import { h, replace } from "../dom.js";
import { pickFolder } from "../folder-picker.js";
import { formatDateTime, formatNumber, t } from "../i18n.js";
import { run } from "../jobs.js";
import { attempt } from "../notice.js";

export async function importer(view) {
  const body = h("div");
  const history = h("section");
  replace(view, h("h1", {}, t("import.title")), h("p", { class: "muted" }, t("import.intro")), body, history);
  drawHistory(history);
  await chooseFolder(body, history);
}

async function chooseFolder(body, history) {
  const folder = await pickFolder(body, { title: t("import.choose_folder") });
  if (folder) await confirm(body, history, folder);
  else replace(body, h("button", { class: "primary", onclick: () => chooseFolder(body, history) }, t("import.choose_folder")));
}

async function confirm(body, history, folder) {
  const [sites, listing] = await Promise.all([get("/sites"), get(`/folders?path=${encodeURIComponent(folder)}&deep=true`)]);
  const site = h(
    "select",
    { id: "site" },
    h("option", { value: "" }, t("import.site_auto")),
    sites.map((s) => h("option", { value: s.id }, s.name)),
  );
  const start = h("button", { class: "primary" }, t("import.start"));
  start.onclick = async () => {
    start.disabled = true;
    replace(body, h("p", {}, t("import.running")));
    const job = await attempt(() =>
      run("/jobs/import", { folder, site_id: site.value ? Number(site.value) : null }),
    );
    if (job?.status === "done") showReport(body, history, job.result);
    else replace(body, h("button", { class: "primary", onclick: () => chooseFolder(body, history) }, t("import.choose_folder")));
    drawHistory(history);
  };
  replace(
    body,
    h(
      "div",
      { class: "card" },
      h("h2", {}, t("import.folder")),
      h("p", { class: "path" }, folder),
      h("p", { class: "muted" }, t("import.in_folder", { n: formatNumber(listing.recordings), count: listing.recordings })),
      h("label", {}, t("import.site"), site),
      h("div", { class: "row" }, start, h("button", { onclick: () => chooseFolder(body, history) }, t("import.other_folder"))),
    ),
  );
}

async function showReport(body, history, report) {
  const sites = await get("/sites");
  const n = (count) => ({ n: formatNumber(count), count });
  const skipped = Object.entries(report.skipped);
  const noSite = report.notices.find((notice) => notice.notice === "no-site");
  const others = report.notices.filter((notice) => notice.notice !== "no-site");

  replace(
    body,
    h(
      "div",
      { class: "card" },
      h("h2", {}, t("import.report")),
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
                h("li", { class: "warn" }, `${formatDateTime(issue.written_at)}: ${t(`config_issue.${issue.issue}`, issue.details)}`),
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
              report.findings.map((finding) =>
                h("li", { class: "muted" }, `${t(`import.problem.${finding.problem}`)} `, h("span", { class: "path" }, finding.file)),
              ),
            ),
          )
        : null,
      report.analysis_job
        ? h("p", {}, t("import.analysis_started"), " ", h("a", { href: "#/" }, t("import.see_results")))
        : null,
    ),
    noSite ? placeSite(report.import_id, noSite, sites, () => drawHistory(history)) : null,
  );
}

// The recordings of an import that matched no site: a new site there, or an existing one.
function placeSite(importId, notice, sites, done) {
  const box = h("div", { class: "card" });
  const where = notice.location;
  const latitude = h("input", { type: "text", inputmode: "decimal", value: where ? where.latitude.toFixed(5) : "" });
  const longitude = h("input", { type: "text", inputmode: "decimal", value: where ? where.longitude.toFixed(5) : "" });
  const name = h("input", {
    type: "text",
    value: where ? t("import.new_site_name", { latitude: where.latitude.toFixed(3), longitude: where.longitude.toFixed(3) }) : "",
  });
  const existing = h("select", {}, sites.map((s) => h("option", { value: s.id }, s.name)));

  const assign = async (site) => {
    const result = await attempt(() => post(`/imports/${importId}/site`, { site_id: site.id }));
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
    h("h2", {}, t("import.new_site")),
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

async function drawHistory(section) {
  const [imports, sites] = await Promise.all([get("/imports"), get("/sites")]);
  replace(
    section,
    h("h2", {}, t("import.history")),
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
