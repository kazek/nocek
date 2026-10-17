// The page: texts first, then the task strip, then whichever screen the address names.

import { get } from "./api.js";
import * as i18n from "./i18n.js";
import { watch } from "./jobs.js";
import { showError } from "./notice.js";
import { quitButton } from "./quit.js";
import { route, start } from "./router.js";
import { devices } from "./views/devices.js";
import { importer } from "./views/import.js";
import { night, nights } from "./views/nights.js";
import { recording } from "./views/recording.js";
import { recordings } from "./views/recordings.js";
import { settings } from "./views/settings.js";
import { sites } from "./views/sites.js";
import { species } from "./views/species.js";
import { welcome } from "./views/welcome.js";

route(/^\/welcome$/, welcome);
route(/^\/settings$/, settings);
route(/^\/import$/, importer);
route(/^\/nights$/, nights);
route(/^\/nights\/(\d{4}-\d{2}-\d{2})$/, night);
route(/^\/recordings$/, recordings);
route(/^\/recording\/(\d+)$/, recording);
route(/^\/sites$/, sites);
route(/^\/devices$/, devices);
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
  quitButton(document.getElementById("quit"), document.getElementById("view"));
  await start(document.getElementById("view"), needsLibrary);
} catch (error) {
  showError(error);
}
