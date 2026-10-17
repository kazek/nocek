// Building elements without innerHTML, so text from files and users stays text.

export function h(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === false || value === null || value === undefined) continue;
    if (name.startsWith("on")) element.addEventListener(name.slice(2), value);
    else if (name === "class") element.className = value;
    else element.setAttribute(name, value === true ? "" : value);
  }
  append(element, children);
  return element;
}

const SVG = "http://www.w3.org/2000/svg";

// The same for SVG, whose elements need their namespace.
export function svg(tag, attributes = {}) {
  const element = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  return element;
}

export function append(element, children) {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : String(child));
  }
  return element;
}

export function replace(element, ...children) {
  element.replaceChildren();
  return append(element, children);
}
