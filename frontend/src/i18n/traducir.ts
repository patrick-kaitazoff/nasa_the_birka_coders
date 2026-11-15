/** Traduce un texto en castellano al inglés con los diccionarios. Puro: lo usan el observador de la pantalla
 * y las pruebas.
 *
 * Orden: 1) coincidencia exacta; 2) plantillas con {0}, {1}… (las partes que cambian se traducen a su vez:
 * un cultivo, «3 de cada 10 años», una ventana de fechas); 3) reglas especiales (fechas con meses, listas);
 * 4) números con coma decimal pasan a punto. Lo que no se reconoce queda como está. */
import { BACKEND } from "./dic-backend";
import { INTERFAZ } from "./dic-interfaz";

const DIC: Record<string, string> = { ...BACKEND, ...INTERFAZ };
const norm = (s: string) => s.replace(/\s+/g, " ").trim();

const EXACTO = new Map<string, string>();
const PLANTILLAS: Array<{ re: RegExp; en: string; literal: number; conPunto: boolean }> = [];
for (const [es, en] of Object.entries(DIC)) {
  const k = norm(es);
  if (!/\{\d+\}/.test(k)) {
    EXACTO.set(k, en);
    continue;
  }
  const partes = k.split(/(\{\d+\})/);
  const orden: number[] = [];
  const fuente = partes.map((p) => {
    const m = p.match(/^\{(\d+)\}$/);
    if (m) { orden.push(+m[1]); return "(.+?)"; }
    return p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("");
  const literal = partes.filter((p) => !/^\{\d+\}$/.test(p)).join("").length;
  const conPunto = k.includes(" · ");
  // el inglés usa los mismos {n}; se guarda en qué grupo de la regex quedó cada uno
  const en2 = en.replace(/\{(\d+)\}/g, (_, n) => `{${orden.indexOf(+n)}}`);
  PLANTILLAS.push({ re: new RegExp(`^${fuente}$`, "sd"), en: en2, literal, conPunto });
}
// las más específicas primero
PLANTILLAS.sort((a, b) => b.literal - a.literal);

const MESES: Record<string, string> = { ene: "Jan", feb: "Feb", mar: "Mar", abr: "Apr", may: "May", jun: "Jun", jul: "Jul", ago: "Aug", sep: "Sep", oct: "Oct", nov: "Nov", dic: "Dec" };
const MES = "(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)";
const RE_FECHA = new RegExp(`^(\\d{1,2}) ${MES}$`);
const RE_FECHA_LARGA = new RegExp(`^(\\d{1,2}) ${MES}\\.? (\\d{4})(,? .*)?$`);
const RE_VENTANA = new RegExp(`^(.+): (\\d{1,2}) ${MES} a (\\d{1,2}) ${MES}$`);
const RE_NUM = /(^|[^\d.,−-])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+)(?![\d])/g;

/** 1.234,5 → 1,234.5 (no toca negativos: las coordenadas llevan punto y signo). */
export function numerosEn(s: string): string {
  return s.replace(RE_NUM, (_, antes: string, n: string) => antes + n.replace(/\./g, "\u0000").replace(/,/g, ".").replace(/\u0000/g, ","));
}

/** «1 years out of 10» → «1 year out of 10»: las plantillas ponen el número en un lugar con el plural fijo.
 * No toca «0.1 years» ni «11 years». */
export function singularEn(s: string): string {
  return s.replace(/(?<![\d.,])1 (year|month|day|time|season|section|plot|crop|rotation)s\b/g, "1 $1");
}

/** ¿El texto fijo de la plantilla (lo que no son huecos) abarca algún « · » del texto? */
function envuelve(k: string, r: RegExpMatchArray): boolean {
  const huecos = ((r as any).indices as Array<[number, number]>).slice(1);
  let ini = -1, fin = -1, pos = 0;
  for (const [a, b] of huecos) {
    if (a > pos) { if (ini < 0) ini = pos; fin = a; }
    pos = Math.max(pos, b);
  }
  if (pos < k.length) { if (ini < 0) ini = pos; fin = k.length; }
  return ini >= 0 && k.slice(ini, fin).includes(" · ");
}

function parentesisAlReves(g: string): boolean {
  let n = 0;
  for (const c of g) {
    if (c === "(") n++;
    else if (c === ")" && --n < 0) return true;
  }
  return false;
}

function parte(s: string, prof: number): string {
  const t = buscar(s, prof);
  if (t != null) return t;
  return lista(s, prof) ?? s;
}

/** «ene, feb y mar», «Soja 1ª, Trigo», «Cebada, Trigo y Colza / canola»: cada pieza tiene que traducirse de verdad
 * (no volver igual), salvo las que no tienen letras. Si alguna no, null. */
function lista(s: string, prof: number): string | null {
  const piezas = s.split(/(, | y )/);
  if (piezas.length < 2) return null;
  const tr = piezas.map((p, i) => {
    if (i % 2) return p === " y " ? " and " : p;
    const t = buscar(p, prof);
    return t != null && (t !== p || !/[a-záéíóúñ]/i.test(p)) ? t : null;
  });
  return tr.every((p) => p != null) ? tr.join("") : null;
}

function buscar(s: string, prof = 0): string | null {
  const k = norm(s);
  if (!k) return null;
  const e = EXACTO.get(k);
  if (e != null) return e;
  // nombre con la primera letra en minúscula, en medio de una frase («…sale es pradera permanente…»)
  if (/^[a-záéíóúñ]/.test(k)) {
    const may = EXACTO.get(k[0].toUpperCase() + k.slice(1));
    if (may != null && /^[A-Z]/.test(may) && !/^[A-Z]{2}/.test(may)) return may[0].toLowerCase() + may.slice(1);
  }
  if (MESES[k]) return MESES[k];
  let m = k.match(RE_FECHA);
  if (m) return `${MESES[m[2]]} ${m[1]}`;
  // fecha y hora de toLocaleString("es-UY"): «, 11:22 a. m.»
  m = k.match(RE_FECHA_LARGA);
  if (m) return `${MESES[m[2]]} ${m[1]}, ${m[3]}${(m[4] || "").replace(/a\. m\./, "AM").replace(/p\. m\./, "PM")}`;
  // «1991 a 2025»
  m = k.match(/^(\d{4}) a (\d{4})$/);
  if (m) return `${m[1]} to ${m[2]}`;
  m = k.match(RE_VENTANA);
  if (m) return `${parte(m[1], prof + 1)}: ${MESES[m[3]]} ${m[2]} to ${MESES[m[5]]} ${m[4]}`;
  if (prof > 3 || k.length > 700) return null;
  for (const p of PLANTILLAS) {
    const r = k.match(p.re);
    // un {n} no puede tragarse el final de una oración y el comienzo de otra
    if (r && r.slice(1).some((g) => /[.!?] [A-ZÁÉÍÓÚ¿]/.test(g))) continue;
    // ni puede quedarse con un paréntesis que cierra antes de abrir: en «grupo CONEAT 8.02 (55 %) y grupo CONEAT D10.3
    // (30 %)», «grupo CONEAT {0} ({1} %)» tomaba la lista entera con {1} = «55 %) y grupo CONEAT D10.3 (30» y la
    // dejaba a medio traducir. Sin esto sigue de largo y la traduce la regla de las listas.
    if (r && r.slice(1).some(parentesisAlReves)) continue;
    // ni tragarse varios pedazos separados con « · » cuando todo el texto fijo de la plantilla queda en uno solo:
    // «pH {0}» se quedaba con «pH 5,8 · MO 3,1 % · arcilla 28 %» y los pedazos quedaban tan adentro que no se
    // traducían. Así los parte la regla de los compuestos, más abajo. Una plantilla que envuelve los pedazos («Cargué
    // el análisis de suelo ({0}). {1}.») sí vale.
    if (r && !p.conPunto && r.slice(1).some((g) => g.includes(" · ")) && !envuelve(k, r)) continue;
    if (r) return p.en.replace(/\{(\d+)\}/g, (_, i) => parte(r[+i + 1], prof + 1));
  }
  // varias oraciones en un mismo texto (el modo guiado las junta): se traduce cada una
  const oraciones = k.split(/(?<=[.!?:]) (?=[A-ZÁÉÍÓÚ¿])/);
  if (oraciones.length > 1) {
    const tr = oraciones.map((o) => buscar(o, prof + 1));
    if (tr.some((x) => x != null)) return oraciones.map((o, i) => tr[i] ?? o).join(" ");
  }
  // la misma frase con o sin el punto final
  if (k.endsWith(".") && !k.endsWith("..")) {
    const sin = buscar(k.slice(0, -1), prof + 1);
    if (sin != null) return sin + ".";
  } else if (!/[.…:]$/.test(k)) {
    const con = EXACTO.get(k + ".");
    if (con != null) return con.replace(/\.$/, "");
  }
  // recortado con «…» en la pantalla: se traduce el texto entero y se recorta igual
  if (k.endsWith("…") && k.length > 24) {
    const pre = k.slice(0, -1);
    for (const [es, en] of EXACTO) if (es.startsWith(pre)) return en.length > pre.length ? en.slice(0, pre.length).trimEnd() + "…" : en;
  }
  // una lista de cosas que se traducen todas, antes de partir por « / »: si no, «Cebada, Trigo y Colza / canola» salía
  // «Cebada, Trigo y Colza / canola» o «Barley, Wheat and Canola / canola»
  const comoLista = lista(k, prof + 1);
  if (comoLista != null) return comoLista;
  // compuestos: «La Loma: Pradera (…)», «2022: Barbecho / Soja de primera · 2023: …». Los nombres propios
  // (potreros, estancias) quedan como están; alcanza con que se traduzca alguna parte.
  // «; » antes que «: »: el historial va «2022: trigo / soja de segunda; 2023: …» y partido primero en «: » quedaban
  // pedazos como «soja de segunda; 2023» sin traducir
  for (const sep of [" · ", "; ", ": ", " / ", " → "]) {
    if (!k.includes(sep)) continue;
    const piezas = k.split(sep);
    const tr = piezas.map((x) => buscar(x, prof + 1));
    if (tr.some((x) => x != null)) return piezas.map((x, i) => tr[i] ?? x).join(sep);
  }
  return null;
}

/** Traduce manteniendo los espacios de los bordes (los nodos de texto de React los traen). */
export function traducir(s: string): string {
  const ya = HECHAS.get(s);
  if (ya !== undefined) return ya;
  const t = traducirSinGuardar(s);
  if (HECHAS.size >= 4000) HECHAS.clear();
  HECHAS.set(s, t);
  return t;
}

// Lo ya traducido se guarda. Un texto que no está entero en el diccionario prueba todas las plantillas,
// las oraciones y las listas (hasta 12 ms uno largo), y el observador vuelve a pedir los mismos textos cada vez que
// React redibuja: en inglés cada paso de la entrevista trababa 0,25 a 0,4 s contra 0,05 s en castellano.
const HECHAS = new Map<string, string>();

function traducirSinGuardar(s: string): string {
  const ini = s.match(/^\s*/)![0];
  const fin = s.slice(ini.length).match(/\s*$/)![0];
  const nucleo = s.slice(ini.length, s.length - fin.length);
  if (!nucleo) return s;
  const t = buscar(nucleo);
  return ini + singularEn(numerosEn(t ?? nucleo)) + fin;
}

/** ¿Quedó castellano sin traducir? Para buscar huecos del diccionario en desarrollo. */
export function pareceCastellano(s: string): boolean {
  return /[áéíóúñ¿¡]/i.test(s) || /\b(de|la|el|los|las|que|con|para|por|del|una|sin|más|tu|tus)\b/i.test(s);
}
