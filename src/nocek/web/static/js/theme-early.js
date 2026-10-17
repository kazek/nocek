// Before anything is drawn: the theme last chosen here, so a dark page does not flash white.
// theme.js takes over once the settings have loaded.
(() => {
  let theme = "system";
  try {
    theme = localStorage.getItem("nocek-theme") || theme;
  } catch {
    // Storage may be unavailable; the system's choice will do.
  }
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.add(dark ? "wa-dark" : "wa-light");
})();
