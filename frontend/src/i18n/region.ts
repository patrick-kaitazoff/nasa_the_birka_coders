/** Textos que dependen del país del campo. La app nació para Uruguay y nombra en muchos lugares el
 * Plan de Uso y Manejo de Suelos del MGAP, que en EE. UU. no existe: allá la misma cuenta (pérdida de suelo de la USLE
 * contra la tolerancia T del suelo) es la que usa el NRCS para la conservación de tierras muy erosionables. En vez de
 * tocar los ~50 textos en 15 archivos, el observador de traducción pasa cada texto por acá después de traducirlo.
 *
 * Cambia algo cuando el campo abierto está en EE. UU. («límite T del NRCS») o en otro país fuera de Uruguay («límite T
 * del suelo»). El país lo fija el store con `useRegion`. */
import { create } from "zustand";
import { conUnidadesUS } from "./unidades";

// "XX": un campo fuera de Uruguay y de EE. UU. (Pucón, el Mosela); "": todavía no hay campo
export type Region = "UY" | "US" | "XX" | "";

export const useRegion = create<{ region: Region; setRegion: (r: Region) => void }>((set) => ({
  region: "",
  setRegion: (region) => set({ region }),
}));

/** ¿El campo abierto está en EE. UU.? Para los componentes que convierten unidades ellos mismos (i18n/unidades.ts). */
export const useUS = () => useRegion((r) => r.region === "US");

/** País por coordenadas, con los mismos rectángulos que el servidor (fuentes/region.py). */
export function regionDe(lat?: number | null, lon?: number | null): Region {
  if (lat == null || lon == null) return "";
  if (lat >= -35.1 && lat <= -30 && lon >= -58.5 && lon <= -53) return "UY";
  if (lat >= 24.4 && lat <= 49.4 && lon >= -125 && lon <= -66.9) return "US";
  return "XX";
}

const AVISO_US_ES =
  "Esto no es un plan de conservación del NRCS: sirve para preparar la conversación con el técnico del NRCS o con un " +
  "asesor certificado. La erosión se calculó con la USLE, el suelo de SSURGO y la tolerancia T de cada suelo, pero el " +
  "factor C sale de las tablas uruguayas de Erosión 6.0: la cifra oficial en EE. UU. se calcula con RUSLE2.";
const AVISO_US_EN =
  "This is not an NRCS conservation plan: it helps prepare the conversation with the NRCS technician or a certified " +
  "adviser. Erosion was calculated with the USLE, SSURGO soils and each soil's T tolerance, but the C factor comes from " +
  "Uruguay's Erosión 6.0 tables: the official U.S. figure is calculated with RUSLE2.";

// [buscar, poner] en orden: primero los textos enteros, después las frases
type Poner = string | ((m: string, ...g: string[]) => string);
const US: Array<[RegExp, Poner]> = [
  [/^Esto no es un Plan de Uso[.:].*$/s, AVISO_US_ES],
  [/^This is not a Soil Use Plan[.:].*$/s, AVISO_US_EN],
  [/Plan de Uso y Manejo( Responsable)? de Suelos/g, "límite T del NRCS"],
  [/Planes de Uso/g, "límites T del NRCS"],
  [/Plan de Uso/g, "límite T del NRCS"],
  [/Uruguay's (official )?Soil Use and (Responsible )?Management Plan/g, "the NRCS soil loss tolerance (T)"],
  [/an MGAP Soil Use Plan/g, "the NRCS soil loss tolerance (T)"],
  [/(the |a )?(official )?(Soil|Land) Use Plans?/g, "the NRCS soil loss tolerance (T)"],
  // la ventana «Análisis listo», el chat y la pantalla de recálculo
  [/datos de la NASA y (del|el) MGAP/g, "datos de la NASA y del USDA"],
  [/NASA and MGAP data/g, "NASA and USDA data"],
  [/los suelos oficiales del MGAP/g, "los suelos de SSURGO (USDA-NRCS)"],
  [/official MGAP soils/g, "SSURGO soils (USDA-NRCS)"],
  [/grupos CONEAT/g, "suelos de SSURGO"],
  [/CONEAT groups/g, "SSURGO soils"],
  [/suelos del MGAP/g, "suelos de SSURGO (USDA-NRCS)"],
  [/Suelo \(MGAP\)/g, "Suelo (SSURGO)"],
  // Caso real de Iowa: el encabezado de Datos decía «the official MGAP soil»
  [/el suelo oficial del MGAP/g, "el suelo de SSURGO (USDA-NRCS)"],
  [/the official MGAP soil/g, "the SSURGO soil (USDA-NRCS)"],
  // en EE. UU. no se dice «de primera»: es maíz o soja a secas, y la de segunda es «double-crop»
  [/First-crop (soybean|corn)/g, (_m: string, c: string) => c[0].toUpperCase() + c.slice(1)],
  [/first-crop (soybean|corn)/g, "$1"],
  [/\b(Soybean|Corn) 1st\b/g, "$1"],
  [/Second-crop/g, "Double-crop"],
  [/second-crop/g, "double-crop"],
];

const AVISO_XX_ES =
  "Esto no es un plan oficial de conservación de suelos: sirve para preparar la conversación con un agrónomo. La " +
  "erosión se calculó con la USLE y el suelo del mapa mundial SoilGrids, con una tolerancia típica de 7 t/ha/año y el " +
  "factor C de las tablas uruguayas de Erosión 6.0.";
const AVISO_XX_EN =
  "This is not an official soil conservation plan: it helps prepare the conversation with an agronomist. Erosion was " +
  "calculated with the USLE and soil from the SoilGrids world map, with a typical tolerance of 7 t/ha/year and the C " +
  "factor from Uruguay's Erosión 6.0 tables.";

// fuera de Uruguay y de EE. UU.: «lo que aguanta el suelo»
const XX: Array<[RegExp, Poner]> = [
  [/^Esto no es un Plan de Uso[.:].*$/s, AVISO_XX_ES],
  [/^This is not a Soil Use Plan[.:].*$/s, AVISO_XX_EN],
  [/Plan de Uso y Manejo( Responsable)? de Suelos/g, "límite T del suelo"],
  [/Planes de Uso/g, "límites T del suelo"],
  [/Plan de Uso/g, "límite T del suelo"],
  [/Uruguay's (official )?Soil Use and (Responsible )?Management Plan/g, "the soil loss tolerance (T)"],
  [/an MGAP Soil Use Plan/g, "the soil loss tolerance (T)"],
  [/(the |a )?(official )?(Soil|Land) Use Plans?/g, "the soil loss tolerance (T)"],
  [/datos de la NASA y (del|el) MGAP/g, "datos de la NASA y de SoilGrids"],
  [/NASA and MGAP data/g, "NASA and SoilGrids data"],
  [/los suelos oficiales del MGAP/g, "los suelos del mapa mundial SoilGrids"],
  [/official MGAP soils/g, "soils from the SoilGrids world map"],
  [/grupos CONEAT/g, "suelos de SoilGrids"],
  [/CONEAT groups/g, "SoilGrids soils"],
  [/el suelo oficial del MGAP/g, "el suelo del mapa mundial SoilGrids"],
  [/the official MGAP soil/g, "the soil from the SoilGrids world map"],
];

export function textoRegional(s: string, region: Region, idioma?: "es" | "en"): string {
  if ((region !== "US" && region !== "XX") || !s) return s;
  // las unidades van primero: las reglas de abajo no tocan números (i18n/unidades.ts)
  let out = region === "US" ? conUnidadesUS(s, idioma) : s;
  for (const [re, poner] of region === "US" ? US : XX) out = out.replace(re, poner as string);
  // «the the NRCS…» cuando el texto ya traía artículo
  return out.replace(/\b(the|The) the (NRCS|soil loss)/g, "$1 $2").replace(/^the (NRCS|soil loss)/, "The $1")
    .replace(/^límite T/, "Límite T");
}
