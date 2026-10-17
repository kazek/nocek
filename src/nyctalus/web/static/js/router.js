// Screens by address: #/settings, #/nights/2026-09-02, #/?site=1 ...
// A screen gets its address's parts, then the query as URLSearchParams.

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
    const [pathname, search = ""] = path.split("?");
    const redirect = await before(pathname);
    if (redirect && redirect !== pathname) return go(redirect);
    for (const link of document.querySelectorAll(".top nav a")) {
      const target = link.getAttribute("href").slice(1);
      const current = target === "/" ? pathname === "/" : pathname.startsWith(target);
      link.toggleAttribute("aria-current", false);
      if (current) link.setAttribute("aria-current", "page");
    }
    for (const { pattern, render } of routes) {
      const match = pathname.match(pattern);
      if (match) {
        view.replaceChildren();
        await render(view, ...match.slice(1).map(decodeURIComponent), new URLSearchParams(search));
        view.focus();
        return;
      }
    }
  };
  addEventListener("hashchange", show);
  return show();
}
