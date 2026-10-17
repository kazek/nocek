// Screens by address: #/settings, #/nights/2026-09-02, ...

const routes = [];

export function route(pattern, render) {
  routes.push({ pattern, render });
}

export function go(path) {
  location.hash = `#${path}`;
}

export function start(view, before) {
  const show = async () => {
    const path = location.hash.slice(1) || "/";
    const redirect = await before(path);
    if (redirect && redirect !== path) return go(redirect);
    for (const link of document.querySelectorAll(".top nav a")) {
      const target = link.getAttribute("href").slice(1);
      const current = target === "/" ? path === "/" : path.startsWith(target);
      link.toggleAttribute("aria-current", false);
      if (current) link.setAttribute("aria-current", "page");
    }
    for (const { pattern, render } of routes) {
      const match = path.match(pattern);
      if (match) {
        view.replaceChildren();
        await render(view, ...match.slice(1).map(decodeURIComponent));
        view.focus();
        return;
      }
    }
  };
  addEventListener("hashchange", show);
  return show();
}
