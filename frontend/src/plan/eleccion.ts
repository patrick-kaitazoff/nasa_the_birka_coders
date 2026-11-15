/** Cuentas de lo que eligió el productor en cada lote: la herramienta sugiere y él elige. Todo sale del análisis que ya está en el navegador, sin pedir nada al servidor. */
import type { Campo, Evaluacion, Plan, SeccionAnalizada } from "../tipos";

/** Cultivos de cosecha: un año cuenta como agrícola si tiene alguno (en el invierno o en el verano). */
const GRANOS = new Set(["soja", "soja2", "maiz", "maiz2", "sorgo", "girasol", "trigo", "cebada", "colza"]);

export function opcionesDe(sec: SeccionAnalizada): Evaluacion[] {
  return [sec.actual, ...sec.alternativas].filter(Boolean) as Evaluacion[];
}

/** Las opciones del lote en el orden en que se muestran, cada una con su nombre corto: «Plan actual» para lo que se
 * hace hoy y «Plan 1», «Plan 2», «Plan 3» para las alternativas, de mayor a menor puntaje. Es el mismo número en
 * Comparar, en el Plan y en el chat de cada lote. */
export function planesDe(sec: SeccionAnalizada): Array<{ ev: Evaluacion; plan: string }> {
  const alts = [...sec.alternativas].sort((a, b) => b.puntaje_total - a.puntaje_total);
  return [
    ...(sec.actual ? [{ ev: sec.actual, plan: "Plan actual" }] : []),
    ...alts.map((ev, i) => ({ ev, plan: `Plan ${i + 1}` })),
  ];
}

/** No se muestran como «Plan 2» o «Plan 3» las alternativas que pierden más suelo del que aguanta. El motor las suma para
 * llegar a tres estrategias por lote; acá se sacan al recibir o abrir un análisis, salvo la sugerida o la elegida (hay
 * lotes donde ninguna entra y se sugiere la que menos erosiona). Empezó solo en los ejemplos; desde ese mismo día
 * vale también para un campo nuevo o guardado. Por qué no hay más opciones lo dice la nota del lote
 * (`nota_tolerancia`), que Comparar muestra al lado de las tarjetas. */
export function sinOpcionesFueraDeTolerancia<A extends { secciones: SeccionAnalizada[] }>(analisis: A, plan: Plan | null): A {
  return {
    ...analisis,
    secciones: analisis.secciones.map((sec) => {
      const p = plan?.secciones.find((x) => x.seccion_id === sec.id);
      const quedan = new Set([sec.recomendada_id, p?.sugerida_id, p?.rotacion_id]);
      const alternativas = sec.alternativas.filter((a) => a.erosion.cumple || quedan.has(a.id));
      return alternativas.length === sec.alternativas.length ? sec : { ...sec, alternativas };
    }),
  };
}

/** El nombre corto («Plan actual», «Plan 2») de una opción del lote. */
export function nombrePlan(sec: SeccionAnalizada, id: string | null | undefined): string | undefined {
  return planesDe(sec).find((x) => x.ev.id === id)?.plan;
}

export function evaluacionDe(sec: SeccionAnalizada, id: string | null | undefined): Evaluacion | undefined {
  return opcionesDe(sec).find((e) => e.id === id);
}

/** Parte de los años de la rotación con algún cultivo de cosecha (0 a 1). */
export function fraccionAgricola(ev: Evaluacion): number {
  if (!ev.anios?.length) return 0;
  return ev.anios.filter(([inv, ver]) => GRANOS.has(inv) || GRANOS.has(ver)).length / ev.anios.length;
}

export function elegidaDe(plan: Plan | null, sec: SeccionAnalizada): string | undefined {
  // sin plan armado, la sugerida
  return plan?.secciones.find((p) => p.seccion_id === sec.id)?.rotacion_id ?? sugeridaDe(plan, sec) ?? (sec.actual ? "actual" : undefined);
}

/** La sugerida de la sección: la del plan (equilibrio agrícola-ganadero) o, en un análisis guardado antes, la mejor
 * según sus prioridades. */
export function sugeridaDe(plan: Plan | null, sec: SeccionAnalizada): string | undefined {
  return plan?.secciones.find((p) => p.seccion_id === sec.id)?.sugerida_id ?? sec.recomendada_id ?? undefined;
}

/** El riesgo que más conviene revisar con el agrónomo: el del Plan de Uso si está, si no el primero. */
export function riesgoPrincipal(ev: Evaluacion): string | undefined {
  const r = ev.explicacion?.riesgos || [];
  return r.find((x) => x.includes("Plan de Uso")) || r[0];
}

export type Cuentas = {
  total: number;
  erosion: number;
  /** lo que aguanta el suelo, promedio del campo pesado por superficie */
  tolerancia: number;
  haSobre: number;
  agricola: number;
  ingreso: number;
  ingresoUsd: boolean;
  /** años de cada uno (0 a 1) en que los cultivos llegan a la floración con menos de la mitad del agua que piden,
   * promedio del campo pesado por superficie */
  seca: number;
  /** lo que pierde un año seco (1 de cada 5) contra el rinde con agua suficiente, pesado por superficie solo entre los
   * lotes con cultivos de cosecha; null si no hay ninguno */
  perdidaSeco: number | null;
};

/** Seca en floración, erosión media, hectáreas por encima de lo que aguanta el suelo, % agrícola e ingreso con una
 * elección por lote. */
export function cuentas(secciones: SeccionAnalizada[], eleccion: (sec: SeccionAnalizada) => string | undefined): Cuentas {
  let total = 0, erosion = 0, tol = 0, haSobre = 0, agr = 0, ing = 0, seca = 0, caida = 0, haCaida = 0;
  const evs: Evaluacion[] = [];
  for (const s of secciones) {
    const ev = evaluacionDe(s, eleccion(s)) || s.actual || s.alternativas[0];
    if (!ev) continue;
    evs.push(ev);
    const ha = s.area_ha || 0;
    total += ha;
    erosion += ev.erosion.a_t_ha * ha;
    tol += (ev.erosion.tolerancia_t || 0) * ha;
    // el campo natural no cuenta: ahí el Plan de Uso no se exige
    if (!ev.erosion.cumple) haSobre += ha;
    agr += fraccionAgricola(ev) * ha;
    seca += (ev.riesgo?.seca ?? 0) * ha;
    if (ev.riesgo?.perdida_anio_seco != null) { caida += ev.riesgo.perdida_anio_seco * ha; haCaida += ha; }
  }
  const ingresoUsd = evs.length > 0 && evs.every((e) => e.ingreso.usa_margenes && e.ingreso.usd_ha_anio != null);
  secciones.forEach((s) => {
    const ev = evaluacionDe(s, eleccion(s)) || s.actual || s.alternativas[0];
    if (!ev) return;
    const v = ingresoUsd ? ev.ingreso.usd_ha_anio ?? 0 : ev.ingreso.indice_relativo ?? 0;
    ing += v * (s.area_ha || 0);
  });
  const t = total || 1;
  return { total, erosion: erosion / t, tolerancia: tol / t, haSobre, agricola: (100 * agr) / t, ingreso: ing / t, ingresoUsd, seca: seca / t,
    perdidaSeco: haCaida > 0 ? caida / haCaida : null };
}

/** Entre las opciones del lote con cultivos de cosecha que no pierden más suelo del que aguanta (el Plan de Uso como
 * condición, no como meta), la de menos seca en floración. Solo con cultivos: una pastura o el campo natural casi no
 * tienen floración que se quede sin agua, y elegirlas «bajaba la seca» dejando el campo sin agricultura (en el
 * ejemplo, 0 % agrícola). Si en el lote no hay ninguna así, queda la sugerida. */
export function menosSecaDentroDelPlan(sec: SeccionAnalizada, sugerida: string | undefined): string | undefined {
  const candidatas = opcionesDe(sec).filter((o) => o.erosion.cumple && fraccionAgricola(o) > 0);
  if (!candidatas.length) return sugerida;
  return candidatas.reduce((a, b) => ((b.riesgo?.seca ?? 1) < (a.riesgo?.seca ?? 1) ? b : a)).id;
}

/** El % agrícola que pidió el productor; en un campo mixto sin dato, 50 % (lo mismo que usa el servidor). */
export function metaAgricola(campo: Campo): number | null {
  const m = campo.objetivos?.pct_agricola;
  if (m != null) return m;
  return campo.sistema?.tipo === "mixto" ? 50 : null;
}

/** «Ver. 26/27» o «Inv. 2027» (Uruguay) y «Ver. 2027» o «Inv. 27/28»: sale de la
 * etiqueta del servidor, que ya dice qué temporada cruza el año. */
export function etiquetaCortaTemporada(t: { tipo: string; anio: number; etiqueta: string }): string {
  const pre = t.tipo === "verano" ? "Ver." : "Inv.";
  const m = /(\d{4})\/(\d{2})/.exec(t.etiqueta || "");
  return m ? `${pre} ${m[1].slice(2)}/${m[2]}` : `${pre} ${t.anio}`;
}
