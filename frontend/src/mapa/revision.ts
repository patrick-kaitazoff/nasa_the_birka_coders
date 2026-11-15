import {
  bbox,
  centroid,
  distance,
  feature,
  transformRotate,
} from "@turf/turf";
import type { Campo, Geo } from "../tipos";
import { anguloLargo, areaHa, recortar } from "./geo";

/**
 * Revisión de las divisiones que ya tiene el campo: avisos en lenguaje llano, sin proponer rehacer nada. Mover un alambrado o una
 * aguada cuesta plata; el productor decide.
 *
 * - Suelos mezclados (grupos CONEAT del MGAP dentro de cada sección).
 * - Forma para la máquina: pasadas cortas (arando, la eficiencia baja de 0,88 con 1.000 m a 0,61 con
 * 250 m; Janulevičius et al.) y formas muy irregulares (pasadas en punta).
 * - Forma y cantidad para el ganado: potreros casi cuadrados (largo menor a 4 veces el ancho) y 6 a 8
 * potreros con agua (NRCS; Virginia Tech 2025).
 */
export type Aviso = { seccion?: string; tipo: "suelo" | "maquina" | "ganado"; texto: string };

/** Largo y ancho (m) del rectángulo más chico que encierra la sección. */
export function medidas(g: Geo): { largo: number; ancho: number; llenado: number } {
  const f = feature(g);
  const centro = centroid(f);
  const girado = transformRotate(f, -anguloLargo(g), { pivot: centro });
  const [x0, y0, x1, y1] = bbox(girado);
  const a = distance([x0, y0], [x1, y0], { units: "meters" });
  const b = distance([x0, y0], [x0, y1], { units: "meters" });
  const largo = Math.max(a, b), ancho = Math.min(a, b);
  const llenado = (areaHa(g) * 10000) / Math.max(largo * ancho, 1);
  return { largo, ancho, llenado };
}

const fmt = (x: number) => x.toLocaleString("es-UY", { maximumFractionDigits: 0 });
/** "10.8a" y "10.8b" son variantes del mismo grupo CONEAT (10.8): para avisar, se compara el grupo. */
const grupoDe = (sc: string) => (sc || "").replace(/[a-zA-Z]+$/, "");
const lista = (xs: string[]) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} y ${xs[xs.length - 1]}`);

export function revisarDivisiones(campo: Campo): Aviso[] {
  const avisos: Aviso[] = [];
  const conGanado = !!campo.sistema?.ganado || campo.sistema?.tipo === "ganadero" || campo.sistema?.tipo === "mixto";
  for (const s of campo.secciones) {
    const ha = s.area_ha || areaHa(s.geometria);
    // suelos mezclados
    if (campo.partes_suelo?.length) {
      // en EE. UU. las partes son unidades de SSURGO («Webster clay loam, Bemis moraine, 0 to 2 percent slopes»):
      // se juntan por el nombre del suelo y no se les dice «grupo CONEAT»
      const us = campo.ubicacion?.pais === "US";
      const clave = (sc: string) => (us ? (sc || "").split(",")[0].trim() : grupoDe(sc));
      const porGrupo = new Map<string, number>();
      for (const p of campo.partes_suelo) {
        const r = recortar(p.geometria, s.geometria);
        if (r) porGrupo.set(clave(p.grupo_coneat), (porGrupo.get(clave(p.grupo_coneat)) || 0) + areaHa(r));
      }
      const grupos = [...porGrupo.entries()].map(([g, h]) => ({ g, ha: h }))
        .filter((x) => x.ha / ha >= 0.2 && x.ha >= 1)
        .sort((a, b) => b.ha - a.ha);
      if (grupos.length >= 2) {
        avisos.push({ seccion: s.nombre, tipo: "suelo", texto: `mezcla suelos distintos: ${lista(grupos.slice(0, 3).map((x) => `${us ? "suelo" : "grupo CONEAT"} ${x.g} (${fmt((100 * x.ha) / ha)} %)`))}. Si se pudieran manejar aparte, cada parte tendría el plan que le conviene a su suelo.` });
      }
    }
    if (ha < 1.5) continue; // muy chica para opinar sobre la forma
    if (s.nombre.startsWith("Pivot")) continue; // los pivots son circulares por diseño: no tiene sentido avisar de la forma
    const m = medidas(s.geometria);
    if (campo.sistema?.tipo !== "ganadero") {
      if (m.largo < 250) avisos.push({ seccion: s.nombre, tipo: "maquina", texto: `las pasadas más largas miden unos ${fmt(m.largo)} m: con pasadas cortas se pierde más tiempo en las vueltas de la cabecera.` });
      else if (m.llenado < 0.55) avisos.push({ seccion: s.nombre, tipo: "maquina", texto: "tiene forma muy despareja: quedan pasadas en punta y más vueltas de máquina." });
    }
    if (conGanado && m.largo / Math.max(m.ancho, 1) > 4) {
      avisos.push({ seccion: s.nombre, tipo: "ganado", texto: `es larga y angosta (${fmt(m.largo)} × ${fmt(m.ancho)} m): como potrero, el ganado se queda cerca del agua y no come parejo. Los potreros pastorean mejor casi cuadrados.` });
    }
  }
  // los avisos iguales de forma, en una sola frase
  const juntar = (tipo: Aviso["tipo"], clave: string, texto: (nombres: string) => string) => {
    const iguales = avisos.filter((a) => a.tipo === tipo && a.texto.startsWith(clave));
    if (iguales.length < 2) return;
    const nombres = lista(iguales.map((a) => a.seccion || ""));
    const resto = avisos.filter((a) => !iguales.includes(a));
    avisos.length = 0;
    avisos.push(...resto, { tipo, texto: texto(nombres) });
  };
  juntar("maquina", "tiene forma muy despareja", (n) => `${n} tienen formas muy desparejas: quedan pasadas en punta y más vueltas de máquina.`);
  juntar("maquina", "las pasadas más largas", (n) => `${n} tienen pasadas cortas (menos de 250 m): se pierde más tiempo en las vueltas de la cabecera.`);
  juntar("ganado", "es larga y angosta", (n) => `${n} son largas y angostas: como potreros, el ganado se queda cerca del agua y no come parejo. Los potreros pastorean mejor casi cuadrados.`);
  if (conGanado && campo.secciones.length > 0 && campo.secciones.length <= 4) {
    avisos.push({ tipo: "ganado", texto: `Con ${campo.secciones.length} ${campo.secciones.length === 1 ? "potrero" : "potreros"} el pasto descansa poco entre pastoreos. Con 6 a 8 potreros con agua en cada uno se aprovecha mejor, y se pueden armar con alambre eléctrico sin obra grande.` });
  }
  return avisos;
}
