// The page: texts first, then the task strip, then whichever screen the address names.

import { get } from "./api.js";
import * as i18n from "./i18n.js";
import { watch } from "./jobs.js";
import { showError } from "./notice.js";
import { route, start } from "./router.js";
import { importer } from "./views/import.js";
import { later } from "./views/later.js";
import { settings } from "./views/settings.js";
import { species } from "./views/species.js";
import { welcome } from "./views/welcome.js";

route(/^\/welcome$/, welcome);
route(/^\/settings$/, settings);
route(/^\/import$/, importer);
route(/^\/nights/, later("nav.nights"));
route(/^\/sites$/, later("nav.sites"));
route(/^\/devices$/, later("nav.devices"));
route(/^\/$/, species);

// Without a library there is nothing to show but the way to make one.
async function needsLibrary(path) {
  if (path === "/welcome" || path === "/settings") return null;
  const library = await get("/library");
  return library.open ? null : "/welcome";
}

try {
  await i18n.load();
  watch()();
  await start(document.getElementById("view"), needsLibrary);
} catch (error) {
  showError(error);
}
