/**
 * Respuestas ya hechas para las preguntas precargadas del chat en los campos de ejemplo. Salen del análisis del lote que se está mirando (el porqué, los riesgos, la erosión, la seca
 * y el ingreso de cada plan), sin llamar a la IA: contestan al instante y siempre igual.
 *
 * Cada renglón es una frase entera, así el traductor de la pantalla la reconoce (los renglones del análisis ya están
 * en el diccionario; los de acá, como plantillas en i18n/dic-interfaz.ts).
 */
import type { Analisis, Evaluacion } from "../tipos";
import { planesDe, riesgoPrincipal } from "../plan/eleccion";

export const POR_QUE_MEJOR = "¿Por qué sale mejor esta opción?";
export const POR_QUE_NO_OTRA = "¿Por qué no otra rotación?";
export const TE_CUENTO = "Te cuento algo que puede cambiar el análisis";
export const MAS_INGRESO = "Quiero más ingreso este año";
// las de seguimiento: aparecen después de tocar la pregunta de la que salen
export const RIESGOS = "¿Qué riesgos tiene?";
export const SUELO = "¿Cuánto suelo se pierde?";
export const ANIO_SECO = "¿Y si viene un año seco?";
export const SEGUIR_HOY = "¿Qué pasa si sigo como hoy?";
export const MAS_OPCIONES = "¿Por qué no hay más opciones?";
export const CUANTO_DEJA = "¿Cuánto deja cada opción?";
export const DE_DONDE = "¿De dónde salen los datos?";
export const PREGUNTAS_EJEMPLO = [POR_QUE_MEJOR, POR_QUE_NO_OTRA, TE_CUENTO, MAS_INGRESO, RIESGOS, SUELO, ANIO_SECO, SEGUIR_HOY, MAS_OPCIONES, CUANTO_DEJA, DE_DONDE];

/** Qué preguntas trae cada respuesta. */
const SIGUEN: Record<string, string[]> = {
  [POR_QUE_MEJOR]: [RIESGOS, SUELO, ANIO_SECO],
  [POR_QUE_NO_OTRA]: [SEGUIR_HOY, MAS_OPCIONES],
  [MAS_INGRESO]: [CUANTO_DEJA],
  [RIESGOS]: [DE_DONDE],
  [SUELO]: [DE_DONDE],
  [ANIO_SECO]: [DE_DONDE],
};

/** Las sugerencias del chat en un ejemplo. La que ya se hizo se va, y en su lugar
 * entran las que siguen de su respuesta, primero las de la última. `hechas`: las ya tocadas en este lote, en orden.
 * `fijas` son las que no se gastan (la de sacar un cultivo, que no manda nada). Solo quedan las que tienen respuesta. */
export function sugerenciasEjemplo(hechas: string[], analisis: Analisis, seccionId: string | null, fijas: string[] = []): string[] {
  const raiz = [POR_QUE_MEJOR, POR_QUE_NO_OTRA, ...fijas, TE_CUENTO, MAS_INGRESO];
  const siguen = [...hechas].reverse().flatMap((h) => SIGUEN[h] || []);
  const todas = [...new Set([...siguen, ...raiz])];
  return todas.filter((q) => !hechas.includes(q) && (fijas.includes(q) || respuestaEjemplo(q, analisis, seccionId) != null)).slice(0, 6);
}

function n(x: number, d = 0) {
  return x.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

const minus = (s: string) => s.replace(/^./, (c) => c.toLowerCase());

function ingreso(ev: Evaluacion): number {
  return ev.ingreso.usa_margenes && ev.ingreso.usd_ha_anio != null ? ev.ingreso.usd_ha_anio : ev.ingreso.indice_relativo ?? 0;
}

function textoIngreso(ev: Evaluacion): string {
  return ev.ingreso.usa_margenes && ev.ingreso.usd_ha_anio != null ? `${n(ev.ingreso.usd_ha_anio)} USD/ha` : n(ev.ingreso.indice_relativo ?? 0, 2);
}

function planDeUso(ev: Evaluacion): string {
  if (ev.erosion.exigible === false) return "en campo natural el Plan de Uso no se exige";
  return ev.erosion.cumple
    ? `cumple con el Plan de Uso (${n(ev.erosion.a_t_ha, 1)} t/ha/año, el suelo aguanta ${n(ev.erosion.tolerancia_t)})`
    : `no cumple con el Plan de Uso (${n(ev.erosion.a_t_ha, 1)} t/ha/año, el suelo aguanta ${n(ev.erosion.tolerancia_t)})`;
}

/** Por qué una opción queda detrás de la mejor del lote, en una frase. `ac`: de cada 100 sorteos de pesos parecidos a
 * los del productor, cuántos sale primera cada una (la sugerida es la que sale primera más seguido, aunque a veces otra
 * puntúe uno o dos puntos más). */
function motivo(ev: Evaluacion, mejor: Evaluacion, ac?: Record<string, number> | null): string {
  if (ev.erosion.exigible !== false && !ev.erosion.cumple) {
    return `no cumple con el Plan de Uso: pierde ${n(ev.erosion.a_t_ha, 1)} t/ha/año y el suelo aguanta ${n(ev.erosion.tolerancia_t)}`;
  }
  if (ev.riesgo.seca > mejor.riesgo.seca + 0.05) {
    return `más años con seca en la floración: ${n(ev.riesgo.seca * 10, 1)} de cada 10, contra ${n(mejor.riesgo.seca * 10, 1)}`;
  }
  if (ac && ac[ev.id] != null && ac[mejor.id] != null && Math.round(ev.puntaje_total) >= Math.round(mejor.puntaje_total)) {
    return `con pesos parecidos a los tuyos sale primera ${ac[ev.id]} de cada 100 veces, contra ${ac[mejor.id]}`;
  }
  return `con tus prioridades puntúa ${Math.round(ev.puntaje_total)} sobre 100, contra ${Math.round(mejor.puntaje_total)}`;
}

/** La respuesta a una de las preguntas precargadas, para el lote `seccionId` (o el primero), o null si no aplica. */
export function respuestaEjemplo(pregunta: string, analisis: Analisis, seccionId: string | null): string | null {
  if (!PREGUNTAS_EJEMPLO.includes(pregunta)) return null;
  const sec = analisis.secciones.find((s) => s.id === seccionId) || analisis.secciones[0];
  if (!sec) return null;
  const planes = planesDe(sec);
  const nombre = (ev: Evaluacion) => planes.find((x) => x.ev.id === ev.id)?.plan || ev.nombre;
  const mejor = planes.find((x) => x.ev.id === sec.recomendada_id)?.ev || planes[0]?.ev;
  if (!mejor) return null;
  const lote = sec.nombre;

  if (pregunta === TE_CUENTO) {
    return [
      "Dale, contame. Escribilo abajo con tus palabras: un lote que se anega, una helada que te pegó o un cultivo que no querés hacer.",
      "Con eso vuelvo a mirar las opciones de cada lote.",
    ].join("\n\n");
  }

  if (pregunta === POR_QUE_MEJOR) {
    const cab = mejor.es_actual
      ? `En ${lote}, lo que mejor encaja con tus prioridades es seguir con lo que hacés hoy (el Plan actual).`
      : `En ${lote}, lo que mejor encaja con tus prioridades es el ${nombre(mejor)}: ${minus(mejor.nombre)}.`;
    const porque = (mejor.explicacion?.por_que || []).slice(0, 3).map((x) => `- ${x}`);
    const datos = `Además, ${planDeUso(mejor)}, y tiene seca en la floración ${n(mejor.riesgo.seca * 10, 1)} de cada 10 años.`;
    const riesgo = riesgoPrincipal(mejor);
    return [cab, porque.join("\n"), datos, // con su mayúscula: así el traductor reconoce el riesgo, que viene del análisis (en minúscula quedaba en castellano), y en su renglón
      riesgo ? `Lo que conviene revisar con tu agrónomo:\n${riesgo}` : ""].filter(Boolean).join("\n\n");
  }

  if (pregunta === POR_QUE_NO_OTRA) {
    const otras = planes.filter((x) => x.ev.id !== mejor.id);
    if (!otras.length) return `En ${lote} no hay otras opciones para comparar.`;
    const cab = `En ${lote}, la que mejor encaja con tus prioridades es el ${nombre(mejor)}. Las otras quedan detrás por esto:`;
    const filas = otras.map((x) => `- ${x.plan}: ${motivo(x.ev, mejor, sec.aceptabilidad)}.`);
    return [cab, filas.join("\n"), "Todas están en Comparar, con su porqué, su evidencia y sus riesgos."].join("\n\n");
  }

  const hoy = sec.actual;

  if (pregunta === RIESGOS) {
    const riesgos = mejor.explicacion?.riesgos || [];
    if (!riesgos.length) return `En ${lote}, ${mejor.es_actual ? "seguir como hoy" : `el ${nombre(mejor)}`} no tiene riesgos marcados. Igual conviene repasarlo con tu agrónomo antes de sembrar.`;
    return [mejor.es_actual ? `Esto es lo que hay que cuidar en ${lote} si seguís como hoy:` : `Esto es lo que hay que cuidar en ${lote} con el ${nombre(mejor)}:`, riesgos.map((x) => `- ${x}`).join("\n"), "Están también en Comparar, en «Por qué, evidencia y riesgos»."].join("\n\n");
  }

  if (pregunta === SUELO) {
    const t = n(mejor.erosion.tolerancia_t);
    if (!hoy || mejor.es_actual) return `En ${lote} se pierden ${n(mejor.erosion.a_t_ha, 1)} t/ha/año de suelo y el suelo aguanta ${t}.`;
    return [
      `Hoy ${lote} pierde ${n(hoy.erosion.a_t_ha, 1)} t/ha/año de suelo y el suelo aguanta ${t}.`,
      `Con el ${nombre(mejor)} pasaría a ${n(mejor.erosion.a_t_ha, 1)} t/ha/año.`,
      "La cuenta usa la pendiente de cada cuadrado del relieve, la fuerza de la lluvia de la zona, el tipo de suelo y cuánto lo cubre cada cultivo mes a mes.",
    ].join("\n\n");
  }

  if (pregunta === ANIO_SECO) {
    const de = mejor.es_actual ? "lo que hacés hoy" : `el ${nombre(mejor)}`;
    const p = mejor.riesgo.perdida_anio_seco;
    return [
      `En ${lote}, con ${de} los cultivos llegan a la floración sin agua suficiente ${n(mejor.riesgo.seca * 10, 1)} de cada 10 años.`,
      p != null ? `En un año seco, de los que toca 1 cada 5, rinde ${n(p * 100)} % menos que con agua suficiente.` : "No tiene cultivos de cosecha, así que un año seco no le saca grano.",
      hoy && !mejor.es_actual ? `Con lo que hacés hoy son ${n(hoy.riesgo.seca * 10, 1)} de cada 10 años.` : "",
    ].filter(Boolean).join("\n\n");
  }

  if (pregunta === SEGUIR_HOY) {
    if (!hoy || mejor.es_actual) return null;
    return [
      `Si seguís como hoy en ${lote}, ${planDeUso(hoy)}.`,
      `Tiene seca en la floración ${n(hoy.riesgo.seca * 10, 1)} de cada 10 años y deja ${textoIngreso(hoy)} de ingreso.`,
      `Con tus prioridades puntúa ${Math.round(hoy.puntaje_total)} sobre 100 y el ${nombre(mejor)} puntúa ${Math.round(mejor.puntaje_total)}.`,
    ].join("\n\n");
  }

  if (pregunta === MAS_OPCIONES) {
    if (!sec.nota_tolerancia) return null;
    return [`${sec.nota_tolerancia}.`, "Por eso en este lote no se muestran como opción: un plan que pierde más suelo del que aguanta no se aprueba."].join("\n\n");
  }

  if (pregunta === CUANTO_DEJA) {
    if (planes.length < 2) return null;
    return [`Esto deja cada opción en ${lote}:`, planes.map((x) => `- ${x.plan}: ${textoIngreso(x.ev)} de ingreso.`).join("\n"),
      planes.some((x) => !x.ev.ingreso.usa_margenes) ? "Sin tus márgenes cargados es un índice relativo: sirve para comparar entre opciones, no es plata." : ""].filter(Boolean).join("\n\n");
  }

  if (pregunta === DE_DONDE) {
    return [
      "De datos abiertos. El relieve, la lluvia, el verdor que ve el satélite y la humedad del suelo son de la NASA.",
      "El tipo de suelo sale del mapa del MGAP en Uruguay, del USDA en Estados Unidos y de SoilGrids en el resto del mundo.",
      "Cada número dice su fuente en la pestaña Datos.",
    ].join("\n\n");
  }

  // MAS_INGRESO
  // entre las que no pierden más suelo del que aguanta: no se propone pasarse de la tolerancia para ganar más
  const entran = planes.filter((x) => x.ev.erosion.cumple || x.ev.erosion.exigible === false);
  const porIngreso = (l: typeof planes) => [...l].sort((a, b) => ingreso(b.ev) - ingreso(a.ev))[0];
  const masIngreso = porIngreso(entran.length ? entran : planes);
  if (masIngreso && masIngreso.ev.id === mejor.id && porIngreso(planes).ev.id !== mejor.id) {
    return `En ${lote}, entre las opciones que no pierden más suelo del que aguanta, la que más ingreso deja ya es la que mejor encaja con tus prioridades: el ${nombre(mejor)}, con ${textoIngreso(mejor)} de ingreso.`;
  }
  if (!masIngreso || masIngreso.ev.id === mejor.id) {
    return `En ${lote}, la que mejor encaja con tus prioridades ya es la que más ingreso deja: el ${nombre(mejor)}, con ${textoIngreso(mejor)} de ingreso.`;
  }
  const ev = masIngreso.ev;
  return [
    `Si este año lo que más te importa es el ingreso, en ${lote} la que más deja es el ${masIngreso.plan}: ${minus(ev.nombre)}, con ${textoIngreso(ev)} de ingreso contra ${textoIngreso(mejor)} del ${nombre(mejor)}.`,
    `A cambio, ${planDeUso(ev)}, y tiene seca en la floración ${n(ev.riesgo.seca * 10, 1)} de cada 10 años.`,
    "Si la querés, elegila en Comparar con «Elegir para el plan».",
  ].join("\n\n");
}
