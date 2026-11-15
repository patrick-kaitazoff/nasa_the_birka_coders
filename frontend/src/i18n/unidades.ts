/** Unidades de EE. UU.. Con un campo en Estados Unidos, lo que se lee en
 * pantalla va en acres, toneladas cortas por acre, dólares por acre, libras por acre y pulgadas. El motor sigue en
 * métrico: acá se convierte el texto ya armado, justo antes de mostrarlo (lo llama `textoRegional`).
 *
 * Regla que evita cifras que no cierran: solo se convierte un número cuando su unidad está en el mismo texto. Un
 * rótulo suelto («t/ha/año» en el encabezado de una tabla) queda como está, y sus números también. Cuando varios
 * números comparten una unidad («de 66,8 a 11,1 t/ha/año», «11,1 de 11 t/ha») se convierten todos. Los pocos números
 * que van sin unidad al lado de otro que sí la lleva («tolerancia del suelo: 11») tienen su regla aparte, abajo.
 *
 * Los rindes en bushels dependen del cultivo: en los textos van en bu/ac cuando el pedazo nombra un solo grano
 * (`rindesEnBushels`) y en lb/ac si no. La tarjeta de márgenes, que sabe el cultivo, usa bushels (ver `LB_POR_BUSHEL`). */

export const HA_A_AC = 2.47105;
/** t/ha → toneladas cortas por acre (la unidad de la tolerancia T del NRCS). */
export const T_HA_A_T_AC = 0.44609;
export const KG_HA_A_LB_AC = 0.892179;
/** Peso oficial del bushel de cada grano, en libras (USDA). El girasol aceitero no tiene uno fijo: se usa 30. */
export const LB_POR_BUSHEL: Record<string, number> = {
  soja: 60, soja2: 60, maiz: 56, maiz2: 56, trigo: 60, cebada: 48, colza: 50, sorgo: 56, girasol: 30,
};
const KG_POR_LB = 0.45359237;
/** bu/ac → kg/ha, USD/bu → USD/t y sus vueltas, para la tarjeta de márgenes. */
export const buAcAKgHa = (bu: number, cultivo: string) => bu * (LB_POR_BUSHEL[cultivo] || 60) * KG_POR_LB * HA_A_AC;
export const kgHaABuAc = (kg: number, cultivo: string) => kg / ((LB_POR_BUSHEL[cultivo] || 60) * KG_POR_LB * HA_A_AC);
export const usdBuAUsdT = (usd: number, cultivo: string) => (usd * 1000) / ((LB_POR_BUSHEL[cultivo] || 60) * KG_POR_LB);
export const usdTAUsdBu = (usd: number, cultivo: string) => (usd * (LB_POR_BUSHEL[cultivo] || 60) * KG_POR_LB) / 1000;

// un número como se escribe en pantalla: «1.314», «1,314», «66,8», «66.8», «50»
const NUM = "\\d{1,3}(?:[.,]\\d{3})+(?!\\d)|\\d+(?:[.,]\\d+)?";
// lo que une varios números que comparten una unidad: «de 66,8 a 11,1», «11.1 of 11», «5-10»
const UNION = "\\s(?:de|of|a|to|contra|vs\\.?)\\s|\\s?[–—-]\\s?|\\s?[→≤≥<>]\\s?";
const CADENA = `(?:${NUM})(?:(?:${UNION})(?:${NUM}))*`;

function leer(num: string): number {
  if (/^\d{1,3}([.,]\d{3})+$/.test(num)) return parseFloat(num.replace(/[.,]/g, ""));
  return parseFloat(num.replace(",", "."));
}

/** Escribe el número con la coma o el punto que traía el texto. */
function escribir(v: number, decimales: number, coma: boolean): string {
  const r = decimales > 0 ? Math.round(v * 10 ** decimales) / 10 ** decimales : Math.round(v);
  const [ent, dec] = r.toFixed(decimales).split(".");
  const entero = Math.abs(r) >= 10000 ? ent.replace(/\B(?=(\d{3})+(?!\d))/g, coma ? "." : ",") : ent;
  const d = dec ? dec.replace(/0+$/, "") : "";
  return d ? `${entero}${coma ? "," : "."}${d}` : entero;
}

/** ¿El texto escribe los decimales con coma? Por los números de la cadena o, si no tienen decimales, por el idioma
 * de la unidad («año», «por»). */
// el idioma de la pantalla, si quien llama lo sabe
let castellano: boolean | undefined;

function usaComa(cadena: string, resto: string): boolean {
  if (/\d,\d{1,2}(?!\d)/.test(cadena)) return true;
  if (/\d\.\d{1,2}(?!\d)/.test(cadena)) return false;
  return castellano ?? /año|por /.test(resto);
}

function convertirCadena(cadena: string, factor: number, decimales: (v: number) => number, coma: boolean, ajustar?: (v: number, n: string) => number): string {
  return cadena.replace(new RegExp(NUM, "g"), (n) => {
    let v = leer(n) * factor;
    if (ajustar) v = ajustar(v, n);
    return isFinite(v) ? escribir(v, decimales(v), coma) : n;
  });
}

/** La tolerancia T del NRCS es un entero de toneladas por acre (1 a 5). El motor la guarda en t/ha (11,2) y la pantalla
 * la muestra sin decimales (11), que al volver da 4,9. Un número de t/ha escrito sin decimales que cae a menos de un
 * cuarto de un entero de t/ac se lleva a ese entero. */
function enteroDeT(v: number, n: string): number {
  if (/[.,]\d{1,2}$/.test(n)) return v;
  const r = Math.round(v);
  return Math.abs(v - r) <= 0.25 ? r : v;
}

const decSuperficie = (v: number) => (v < 20 ? 1 : 0);
const decErosion = (v: number) => (v < 100 ? 1 : 0);
const decEntero = () => 0;
// lluvia en pulgadas con un decimal, igual que las cifras y los gráficos de Datos (`medidas`)
const decPulgadas = (v: number) => (v < 100 ? 1 : 0);

type Regla = { re: RegExp; factor: number; dec: (v: number) => number; unidad: (u: string) => string; ajustar?: (v: number, n: string) => number; erosion?: boolean };
const antes = "(^|[^\\d.,/\\w])";
const REGLAS: Regla[] = [
  // erosión y tolerancia: t/ha → t/ac (toneladas cortas)
  { re: new RegExp(`${antes}(${CADENA})(\\s?)t\\/ha\\b`, "g"), factor: T_HA_A_T_AC, dec: decErosion, unidad: () => "t/ac", ajustar: enteroDeT, erosion: true },
  // plata por superficie
  { re: new RegExp(`${antes}(${CADENA})(\\s?)(USD|US\\$)\\/ha\\b`, "g"), factor: 1 / HA_A_AC, dec: decEntero, unidad: (u) => `${u}/ac` },
  // rindes y dosis
  { re: new RegExp(`${antes}(${CADENA})(\\s?)kg\\/ha\\b`, "g"), factor: KG_HA_A_LB_AC, dec: decEntero, unidad: () => "lb/ac" },
  // superficies
  { re: new RegExp(`${antes}(${CADENA})(\\s?)(ha|hectáreas|hectares)\\b(?!\\/)`, "g"), factor: HA_A_AC, dec: decSuperficie, unidad: (u) => (u === "ha" ? "ac" : "acres") },
  // lluvia y agua del suelo
  { re: new RegExp(`${antes}(${CADENA})(\\s?)mm\\b`, "g"), factor: 1 / 25.4, dec: decPulgadas, unidad: () => "in" },
];

// números que van sin unidad porque la lleva otro número de la misma frase: todos son toneladas por hectárea
const SIN_UNIDAD: RegExp[] = [
  new RegExp(`((?:tolerancia del suelo|soil tolerance|tolerancia|tolerance):\\s)(${NUM})(?!\\s?(?:t\\/|\\d|[.,]\\d))`, "g"),
  new RegExp(`((?:y aguanta|and can take|aguanta|can take)\\s)(${NUM})(?!\\s?(?:t\\/|\\d|[.,]\\d))`, "g"),
  // «por encima de la tolerancia del suelo (11)», «cerca de la tolerancia (11)», «…, tolerancia 7)»
  new RegExp(`((?:tolerancia(?: del suelo)?|tolerance)\\s\\(?)(${NUM})(?!\\s?(?:t\\/|\\d|[.,]\\d))`, "g"),
];

/** Para gráficos y cifras donde el número y la unidad van en nodos distintos y el texto no se puede convertir entero: cada componente convierte el valor y escribe la unidad. En EE. UU., pulgadas con un decimal y °F. */
export function medidas(us: boolean) {
  return us
    ? { agua: (mm: number) => mm / 25.4, decAgua: 1, uAgua: "in", temp: (c: number) => c * 1.8 + 32, difTemp: (c: number) => c * 1.8, uTemp: "°F" }
    : { agua: (mm: number) => mm, decAgua: 0, uAgua: "mm", temp: (c: number) => c, difTemp: (c: number) => c, uTemp: "°C" };
}

/** °C → °F. Una temperatura (35 °C → 95 °F) lleva el corrimiento de 32; una diferencia (+1,5 °C, «10 °C de
 * diferencia», «2-4 °C más fría») solo se multiplica por 1,8. Es diferencia si lleva «+» o si la frase sigue con
 * «más», «menos», «de diferencia», «entre», «warmer», «cooler», etc. */
export const cAF = (c: number) => c * 1.8 + 32;
const DIFERENCIA_DESPUES = /^\s*(más|menos|de diferencia|entre|de cambio|warmer|cooler|colder|hotter|higher|lower|more|less|of difference|difference|between|apart)\b/i;
const TEMP = new RegExp(`${antes}([+\\-−]?)(${CADENA})(\\s?)°C(?![a-zA-Z])`, "g");

function temperaturas(s: string): string {
  return s.replace(TEMP, (t, pre: string, signo: string, cadena: string, espacio: string, pos: number, todo: string) => {
    const despues = todo.slice(pos + t.length);
    const diferencia = signo === "+" || DIFERENCIA_DESPUES.test(despues);
    const coma = usaComa(cadena, todo);
    let primero = true;
    const nueva = cadena.replace(new RegExp(NUM, "g"), (n) => {
      // el signo menos de una temperatura va solo con el primer número («-3 °C», «-3 a 2 °C»)
      const v = leer(n) * (primero && signo && signo !== "+" && !diferencia ? -1 : 1);
      primero = false;
      const dec = /[.,]\d+$/.test(n) && !/^\d{1,3}([.,]\d{3})+$/.test(n) ? 1 : 0;
      return escribir(diferencia ? v * 1.8 : cAF(v), dec, coma);
    });
    // una diferencia conserva su signo; una temperatura ya lo lleva en el número en °F
    return `${pre}${diferencia ? signo : ""}${nueva}${espacio}°F`;
  });
}

/** Rindes en bushels cuando el pedazo de texto nombra un solo grano. Se mira cada pedazo separado por
 * «; » («soja 1.900 kg/ha (esperás 2.600); maíz 5.000 kg/ha»): si nombra exactamente un cultivo, sus kg/ha pasan a
 * bu/ac con el peso del bushel de ese grano, y también el «(esperás 2.600)» que va sin unidad. Si no nombra ninguno o
 * nombra dos, queda para la regla general (lb/ac). */
const GRANOS: Array<[RegExp, string]> = [
  [/\b(soja|soybeans?)\b/i, "soja"],
  [/(\bmaíz\b|\bmaiz\b|\bcorn\b)/i, "maiz"],
  [/\b(trigo|wheat)\b/i, "trigo"],
  [/\b(cebada|barley)\b/i, "cebada"],
  [/\b(sorgo|sorghum)\b/i, "sorgo"],
  [/\b(girasol|sunflower)\b/i, "girasol"],
  [/\b(colza|canola|rapeseed)\b/i, "colza"],
];

function rindesEnBushels(s: string): string {
  return s.split(/(;\s)/).map((pedazo) => {
    if (!/kg\/ha/.test(pedazo)) return pedazo;
    const hay = GRANOS.filter(([re]) => re.test(pedazo));
    if (hay.length !== 1) return pedazo;
    const cultivo = hay[0][1];
    const coma = usaComa(pedazo, s);
    const aBu = (n: string) => escribir(kgHaABuAc(leer(n), cultivo), 0, coma);
    return pedazo
      .replace(new RegExp(`${antes}(${CADENA})(\\s?)kg\\/ha\\b`, "g"), (_t, pre: string, cadena: string, esp: string) =>
        `${pre}${cadena.replace(new RegExp(NUM, "g"), aBu)}${esp}bu/ac`)
      .replace(new RegExp(`\\((esperás|you expect) (${NUM})\\)`, "g"), (_t, pal: string, n: string) => `(${pal} ${aBu(n)})`);
  }).join("");
}

export function conUnidadesUS(s: string, idioma?: "es" | "en"): string {
  castellano = idioma ? idioma === "es" : undefined;
  if (!/\d/.test(s)) {
    return s.replace(/por hectárea/g, "por acre").replace(/per hectare/g, "per acre");
  }
  let out = /°C/.test(s) ? temperaturas(s) : s;
  // primero los sueltos: después de convertir los otros ya no se sabe si la frase estaba en t/ha
  if (/t\/ha/.test(out)) {
    const coma = castellano ?? (/año|por /.test(out) || /\d,\d{1,2}(?!\d)/.test(out));
    for (const re of SIN_UNIDAD) {
      out = out.replace(re, (_t, pre: string, n: string) => pre + escribir(enteroDeT(leer(n) * T_HA_A_T_AC, n), 1, coma));
    }
  }
  // dos textos donde la erosión se deja en t/ha:
  // - la ecuación «A = R 350 × K 0,369 × LS 0,70 × C 0,216 × P 1,0 = 19,5 t/ha/año»: R y K están en unidades métricas y
  // la cuenta tiene que cerrar; se agrega el equivalente al final;
  // - la ficha de SSURGO, que ya dice «T 5 t/acre/año (11,2 t/ha)».
  const ecuacion = /A = R [\d.,]+ × K/.test(out);
  const yaEnAcres = /t\/acre/.test(out);
  if (ecuacion) {
    out = out.replace(new RegExp(`(${NUM})(\\s?t\\/ha(?:\\/(?:año|yr|year))?)`, "g"), (t, n: string, u: string) =>
      `${t} (${escribir(leer(n) * T_HA_A_T_AC, 1, /,\d/.test(n) || /año/.test(u))}${u.replace("t/ha", "t/ac")})`);
  }
  // la renta en soja: «800 kg de soja» (por hectárea) → bushels de soja por acre, y «soja a 400 USD/t» → USD/bu
  if (/kg (de soja|of soybeans)|(soja a|soybeans at) [\d.,]+ USD\/t/.test(out)) {
    out = out.replace(new RegExp(`(${NUM}) kg (de soja|of soybeans)`, "g"), (_t, n: string, de: string) =>
      `${escribir(kgHaABuAc(leer(n), "soja"), 0, false)} bu ${de}`);
    out = out.replace(/\bbu (de soja|of soybeans) (por|per) ha\b/g, "bu $1 $2 acre");
    out = out.replace(new RegExp(`(soja a|soybeans at) (${NUM}) USD\\/t`, "g"), (_t, pre: string, n: string) =>
      `${pre} ${escribir(usdTAUsdBu(leer(n), "soja"), 2, /soja a/.test(pre))} USD/bu`);
  }
  if (/kg\/ha/.test(out)) out = rindesEnBushels(out);
  // «402 USD/ha/año (350 descontando años de seca)»: el segundo también es plata por hectárea
  if (/USD\/ha/.test(out)) {
    out = out.replace(new RegExp(`\\((-?)(${NUM})(\\s(?:descontando años de seca|after discounting drought years)\\))`, "g"),
      (_t, signo: string, n: string, resto: string) => `(${signo}${escribir(leer(n) / HA_A_AC, 0, false)}${resto}`);
  }
  for (const r of REGLAS) {
    if (r.erosion && (ecuacion || yaEnAcres)) continue;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    out = out.replace(r.re, (...g: any[]) => {
      const [, pre, cadena, espacio] = g as string[];
      // con cuatro grupos el último es la unidad tal cual vino (USD, ha, hectáreas)
      const unidadVino = typeof g[4] === "string" ? g[4] : "";
      const coma = usaComa(cadena, out);
      return `${pre}${convertirCadena(cadena, r.factor, r.dec, coma, r.ajustar)}${espacio}${r.unidad(unidadVino)}`;
    });
  }
  return out.replace(/por hectárea/g, "por acre").replace(/per hectare/g, "per acre");
}
