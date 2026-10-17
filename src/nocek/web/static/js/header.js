// The header's tools: the language, the theme, the settings, and quitting.

import { get, put } from "./api.js";
import { openDialog } from "./dialog.js";
import { h, replace } from "./dom.js";
import { t } from "./i18n.js";
import { attempt } from "./notice.js";
import { quitButton } from "./quit.js";
import { THEMES, applyTheme, currentTheme } from "./theme.js";
import { settings as settingsPanel } from "./views/settings.js";

const THEME_ICONS = { system: "sun-moon", light: "sun", dark: "moon" };

export async function tools(container, view) {
  const [settings, locales] = await Promise.all([get("/settings"), get("/locales")]);
  applyTheme(settings.theme);
  const quit = h(
    "wa-button",
    { appearance: "plain", size: "small" },
    h("wa-icon", { slot: "start", name: "power" }),
    t("header.quit"),
  );
  quitButton(quit, view);
  const gear = h(
    "wa-button",
    { appearance: "plain", size: "small", onclick: () => openDialog(t("settings.title"), settingsPanel, { wide: true }) },
    h("wa-icon", { name: "settings", label: t("settings.title") }),
  );
  replace(container, languageMenu(settings, locales), themeMenu(), gear, quit);
}

function languageMenu(settings, locales) {
  const item = (value, label) =>
    h("wa-dropdown-item", { type: "checkbox", value, checked: (settings.language ?? "") === value }, label);
  const menu = h(
    "wa-dropdown",
    { placement: "bottom-end" },
    h(
      "wa-button",
      { slot: "trigger", appearance: "plain", size: "small", "with-caret": true },
      h("wa-icon", { slot: "start", name: "languages", label: t("header.language") }),
      locales.available[locales.chosen],
    ),
    item("", t("settings.follow_browser")),
    h("wa-divider"),
    Object.entries(locales.available).map(([code, name]) => item(code, name)),
  );
  menu.addEventListener("wa-select", async (event) => {
    const code = event.detail.item.value;
    const change = code ? { language: code } : { follow_browser_language: true };
    if (await attempt(() => put("/settings", change))) location.reload();
  });
  return menu;
}

function themeMenu() {
  const icon = h("wa-icon", { name: THEME_ICONS[currentTheme()], label: t("header.theme") });
  const items = THEMES.map((theme) =>
    h(
      "wa-dropdown-item",
      { type: "checkbox", value: theme, checked: theme === currentTheme() },
      h("wa-icon", { slot: "icon", name: THEME_ICONS[theme] }),
      t(`theme.${theme}`),
    ),
  );
  const menu = h(
    "wa-dropdown",
    { placement: "bottom-end" },
    h("wa-button", { slot: "trigger", appearance: "plain", size: "small" }, icon),
    items,
  );
  menu.addEventListener("wa-select", (event) => {
    const theme = event.detail.item.value;
    applyTheme(theme);
    icon.name = THEME_ICONS[theme];
    for (const item of items) item.checked = item.value === theme;
    attempt(() => put("/settings", { theme }));
  });
  return menu;
}
