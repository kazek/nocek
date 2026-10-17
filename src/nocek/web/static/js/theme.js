// Light, dark, or whatever the system uses: Web Awesome's wa-light / wa-dark class on <html>.

export const THEMES = ["system", "light", "dark"];

const system = matchMedia("(prefers-color-scheme: dark)");
let chosen = "system";

export function applyTheme(theme) {
  chosen = THEMES.includes(theme) ? theme : "system";
  try {
    localStorage.setItem("nocek-theme", chosen); // for theme-early.js on the next load
  } catch {
    // Without storage the page may flash the other theme while loading; nothing worse.
  }
  paint();
}

export function currentTheme() {
  return chosen;
}

function paint() {
  const dark = chosen === "dark" || (chosen === "system" && system.matches);
  document.documentElement.classList.toggle("wa-dark", dark);
  document.documentElement.classList.toggle("wa-light", !dark);
}

system.addEventListener("change", paint);
