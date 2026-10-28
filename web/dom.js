export const $ = (id) => document.getElementById(id);
export const format = (value, digits = 2) =>
  Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
export const colors = ["#37c964", "#58bde8", "#eab85c", "#c68be8"];
const SVG_NS = "http://www.w3.org/2000/svg";
export function svg(tag, attributes, parent) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  parent.append(element);
  return element;
}
export function svgText(x, y, text, parent, attributes = {}) {
  const element = svg("text", { x, y, ...attributes }, parent);
  element.textContent = text;
  return element;
}
