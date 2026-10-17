// Screens by address: #/welcome, #/?device=1&night=2026-09-02 ...
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
    for (const { pattern, render } of routes) {
      const match = pathname.match(pattern);
      if (match) {
        view.replaceChildren();
        await render(view, ...match.slice(1).map(decodeURIComponent), new URLSearchParams(search));
        view.focus({ preventScroll: true });
        return;
      }
    }
    go("/"); // an address from an older version, say
  };
  addEventListener("hashchange", show);
  return show();
}
