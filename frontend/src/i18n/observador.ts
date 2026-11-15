/** Traduce lo que se ve en la pantalla sin tocar los componentes: mira el DOM (MutationObserver) y cambia
 * los textos y algunos atributos (placeholder, title, aria-label, alt) según el idioma elegido. Guarda el
 * original de cada nodo para volver al castellano sin recargar.
 *
 * Por qué así y no con t("…") en cada componente: la app tiene ~1.000 textos repartidos en 25 archivos que
 * se siguen editando; envolver cada uno cruzaría con todo el trabajo en curso. React cambia el texto de un
 * nodo solo cuando su valor cambia en el código, y ahí el observador lo vuelve a traducir.
 *
 * No se tocan: lo que escribe el usuario (inputs, textarea), <script>/<style>, ni lo marcado con
 * data-no-traducir. */
import { useIdioma } from "./idioma";
import { textoRegional, useRegion } from "./region";
import { pareceCastellano, traducir } from "./traducir";

const ATRIBUTOS = ["placeholder", "title", "aria-label", "alt"];
const original = new WeakMap<Node, string>();
const puesto = new WeakMap<Node, string>();
const attrOriginal = new WeakMap<Element, Map<string, string>>();
const attrPuesto = new WeakMap<Element, Map<string, string>>();
const faltan = new Set<string>();

const idioma = () => useIdioma.getState().idioma;
// Después de traducir, lo que cambia según el país del campo (i18n/region.ts)
const regional = (s: string) => textoRegional(s, useRegion.getState().region, idioma());

function excluido(n: Node): boolean {
  const el = n.nodeType === Node.ELEMENT_NODE ? (n as Element) : n.parentElement;
  return !el || !!el.closest("script,style,textarea,[data-no-traducir],[contenteditable=true]");
}

function sinAtributos(n: Node): boolean {
  const el = n.nodeType === Node.ELEMENT_NODE ? (n as Element) : n.parentElement;
  return !el || !!el.closest("[data-no-traducir]");
}

function texto(n: Text) {
  const actual = n.nodeValue ?? "";
  if (puesto.get(n) !== actual) original.set(n, actual);
  const orig = original.get(n) ?? actual;
  const traducido = idioma() === "en" ? traducir(orig) : orig;
  const nuevo = regional(traducido);
  if (import.meta.env.DEV && idioma() === "en" && traducido === orig && orig.trim() && pareceCastellano(orig)) faltan.add(orig.trim());
  puesto.set(n, nuevo);
  if (actual !== nuevo) n.nodeValue = nuevo;
}

function atributos(el: Element) {
  for (const a of ATRIBUTOS) {
    const actual = el.getAttribute(a);
    if (actual == null) continue;
    const orig = attrOriginal.get(el) ?? new Map<string, string>();
    const puestos = attrPuesto.get(el) ?? new Map<string, string>();
    if (puestos.get(a) !== actual) orig.set(a, actual);
    const nuevo = regional(idioma() === "en" ? traducir(orig.get(a)!) : orig.get(a)!);
    puestos.set(a, nuevo);
    attrOriginal.set(el, orig);
    attrPuesto.set(el, puestos);
    if (actual !== nuevo) el.setAttribute(a, nuevo);
  }
}

function recorrer(raiz: Node) {
  if (raiz.nodeType === Node.TEXT_NODE) {
    if (!excluido(raiz)) texto(raiz as Text);
    return;
  }
  if (raiz.nodeType !== Node.ELEMENT_NODE) return;
  // los atributos (placeholder de un textarea, por ejemplo) se traducen aunque el contenido no
  if (!sinAtributos(raiz)) atributos(raiz as Element);
  (raiz as Element).querySelectorAll(ATRIBUTOS.map((a) => `[${a}]`).join(",")).forEach((el) => { if (!sinAtributos(el)) atributos(el); });
  if (excluido(raiz)) return;
  const w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) if (!excluido(n)) texto(n as Text);
}

let tituloOriginal = "";
function titulo() {
  if (!tituloOriginal || (document.title !== traducir(tituloOriginal) && document.title !== tituloOriginal)) tituloOriginal = document.title;
  document.title = idioma() === "en" ? traducir(tituloOriginal) : tituloOriginal;
}

export function iniciarTraduccion() {
  const obs = new MutationObserver((cambios) => {
    for (const c of cambios) {
      if (c.type === "characterData") { if (!excluido(c.target)) texto(c.target as Text); }
      else if (c.type === "attributes") { if (!sinAtributos(c.target)) atributos(c.target as Element); }
      else c.addedNodes.forEach(recorrer);
    }
  });
  obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATRIBUTOS });
  const aplicar = () => {
    document.documentElement.lang = idioma();
    titulo();
    recorrer(document.body);
  };
  aplicar();
  useIdioma.subscribe(aplicar);
  useRegion.subscribe(aplicar);
  // window.confirm y alert no pasan por el DOM
  const confirmar = window.confirm.bind(window);
  window.confirm = (m?: string) => confirmar(m && idioma() === "en" ? traducir(m) : m);
  const alertar = window.alert.bind(window);
  window.alert = (m?: string) => alertar(m && idioma() === "en" ? traducir(m) : m);
  if (import.meta.env.DEV) (window as unknown as { __sinTraducir: Set<string> }).__sinTraducir = faltan;
}
