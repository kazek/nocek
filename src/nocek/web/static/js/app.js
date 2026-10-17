// The page: texts first, then the header, then the main page, or the welcome until
// there is a library.

import { registerIconLibrary } from "../vendor/webawesome/webawesome.js";
import { get } from "./api.js";
import { tools } from "./header.js";
import * as i18n from "./i18n.js";
import { watch } from "./jobs.js";
import { showError } from "./notice.js";
import { route, start } from "./router.js";
import { home } from "./views/home.js";
import { welcome } from "./views/welcome.js";

route(/^\/welcome$/, welcome);
route(/^\/$/, home);

// Icons come from the copy of Lucide that ships with Nocek, never from the network.
registerIconLibrary("default", { resolver: (name) => `/static/vendor/lucide/${name}.svg` });

// Without a library there is nothing to show but the way to make one.
async function needsLibrary(path) {
  if (path === "/welcome") return null;
  const library = await get("/library");
  return library.open ? null : "/welcome";
}

try {
  await i18n.load();
  watch()();
  await tools(document.getElementById("tools"), document.getElementById("view"));
  await start(document.getElementById("view"), needsLibrary);
} catch (error) {
  showError(error);
}
