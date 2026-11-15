import { nombreCultivo, useApp } from "../store";
import { GraficoAntesAhora, GraficoLluviaET, GraficoNDVI, GraficoTormentasMes, type FilaCultivoAntesAhora } from "./Graficos";
function calcularHallazgoFuerte(codigos: string[], tCultivos: Record<string, any>, catalogo: any): string {
  interface Cand {
    cod: string;
    tipo: "seca" | "calor";
    dif: number;
    antes: number;
    ahora: number;
  }
  const cands: Cand[] = [];
  for (const c of codigos) {
    const cult = tCultivos[c];
    if (!cult) continue;
    if (cult.prob_seca && cult.prob_seca.antes != null && cult.prob_seca.ahora != null) {
      const ps = cult.prob_seca;
      const esClaro = ps.cambio_claro ?? (Math.abs(ps.ahora - ps.antes) >= 0.2);
      if (esClaro) {
        cands.push({ cod: c, tipo: "seca", dif: ps.ahora - ps.antes, antes: ps.antes, ahora: ps.ahora });
      }
    }
    if (cult.prob_calor && cult.prob_calor.antes != null && cult.prob_calor.ahora != null) {
      const pc = cult.prob_calor;
      const esClaro = pc.cambio_claro ?? (Math.abs(pc.ahora - pc.antes) >= 0.2);
      if (esClaro) {
        cands.push({ cod: c, tipo: "calor", dif: pc.ahora - pc.antes, antes: pc.antes, ahora: pc.ahora });
      }
    }
  }

  // Priorizar aumentos claros de riesgo (dif > 0)
  cands.sort((a, b) => b.dif - a.dif);
  if (cands.length > 0 && cands[0].dif >= 0.2 - 1e-4) {
    const top = cands[0];
    const nom = nombreCultivo(catalogo, top.cod, true).toLowerCase();
    const dAnt = Math.round(top.antes * 10);
    const dAho = Math.round(top.ahora * 10);
    if (top.tipo === "seca") {
      return `En ${nom}, la seca en floración pasó de ${dAnt} a ${dAho} años de cada 10.`;
    } else {
      return `En ${nom}, el calor en floración pasó de ${dAnt} a ${dAho} años de cada 10.`;
    }
  }

  const mejoras = cands.filter((c) => c.dif <= -0.2 + 1e-4);
  if (mejoras.length > 0) {
    mejoras.sort((a, b) => a.dif - b.dif);
    const top = mejoras[0];
    const nom = nombreCultivo(catalogo, top.cod, true).toLowerCase();
    const dAnt = Math.round(top.antes * 10);
    const dAho = Math.round(top.ahora * 10);
    const que = top.tipo === "seca" ? "la seca en floración" : "el calor en floración";
    return `En ${nom}, ${que} bajó de ${dAnt} a ${dAho} años de cada 10.`;
  }

  return "No se observan cambios claros en los cultivos del plan.";
}

import { DiezAnios } from "./DiezAnios";
import { Escenario } from "./Escenario";
import { Glosario } from "./Glosario";
import { Humedad, useSmap } from "./Humedad";
import { Ecostress } from "./Ecostress";
import { RelieveDatos } from "./RelieveDatos";
import { MetodosDescubierto, useMetodosDescubierto } from "./MetodosDescubierto";
import { Termino, irA } from "./Termino";
import { CreerleALaApp } from "./CreerleALaApp";
import { useUS } from "../i18n/region";
import { medidas } from "../i18n/unidades";

/** Los grupos de la pestaña Datos, en el orden de las preguntas que se hace el productor. */
const GRUPOS: Array<{ id: string; t: string }> = [
  { id: "datos-g-importa", t: "Lo que más importa" },
  { id: "datos-g-clima", t: "Tu clima" },
  { id: "datos-g-riesgo", t: "Riesgo de cada cultivo" },
  { id: "datos-g-agua", t: "El agua en tu suelo" },
  { id: "datos-g-secciones", t: "Sección por sección" },
  { id: "datos-g-creer", t: "¿Le podemos creer?" },
  { id: "datos-g-agronomo", t: "Para el agrónomo" },
];

interface Hallazgo { texto: string; destino: string; seccion?: string }

function fmt(n: number | null | undefined, d = 0) {
  if (n == null) return "s/d";
  return n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

function formatearFecha(iso: string) {
  const partes = iso.split("-");
  if (partes.length !== 3) return iso;
  return `${parseInt(partes[2], 10)}/${parseInt(partes[1], 10)}/${partes[0]}`;
}

const MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

/** Los meses en que se evapora más de lo que llueve, del promedio mes a mes. El tramo más largo, dando la vuelta al año. */
function mesesQueSeSeca(mensual: Array<{ lluvia_mm: number; et0_mm: number }>): string {
  const seco = mensual.map((m) => m.et0_mm > m.lluvia_mm);
  const n = seco.length;
  if (n !== 12 || !seco.some(Boolean)) return "en promedio, ningún mes se va más agua de la que llueve";
  if (seco.every(Boolean)) return "todos los meses se va más agua de la que llueve";
  let ini = 0, largo = 0;
  for (let i = 0; i < n; i++) {
    if (!seco[i] || seco[(i + n - 1) % n]) continue;
    let k = 0;
    while (seco[(i + k) % n]) k++;
    if (k > largo) { ini = i; largo = k; }
  }
  const fin = (ini + largo - 1) % n;
  return largo === 1 ? `en ${MESES_LARGOS[ini]} se va más agua de la que llueve`
    : `de ${MESES_LARGOS[ini]} a ${MESES_LARGOS[fin]} se va más agua de la que llueve`;
}

function de10(p: number, corto = false) {
  const n = Math.round(10 * p);
  if (n === 0) return corto ? "menos de 1 de cada 10" : "menos de 1 año de cada 10";
  return corto ? `${n} de cada 10` : n === 1 ? "1 año de cada 10" : `${n} años de cada 10`;
}


export function PanelAnalisis() {
  const { analisis, catalogo, campo, plan, datosSeccion: sec, setDatosSeccion: setSec, datosAgronomo, setDatosAgronomo, esEjemplo } = useApp();
  const secVista = analisis ? analisis.secciones.find((x) => x.id === sec) || analisis.secciones[0] : undefined;
  const metodos = useMetodosDescubierto(secVista?.ndvi || {});
  const smap = useSmap();
  // en EE. UU. las cifras de lluvia van en pulgadas (el número y la unidad están en nodos distintos)
  const u = medidas(useUS());
  if (!analisis) {
    return <div className="vacio"><div className="caja"><h3>Sin análisis todavía</h3><p>El análisis corre cuando están el contorno del campo y lo principal de la entrevista. También lo podés pedir en el chat.</p></div></div>;
  }
  const cl = analisis.clima;
  const t = cl.tendencia;
  const z = cl.zafra_actual;
  const et0Anual = cl.mensual.reduce((a: number, m: any) => a + m.et0_mm, 0);
  const s = analisis.secciones.find((x) => x.id === sec) || analisis.secciones[0];

  const riesgos = Object.entries(cl.riesgos_cultivo as Record<string, any>).filter(([cod]) => !["cobertura", "verdeo"].includes(cod));
  const est = campo.estacion?.comparacion;
  // «El agua en tu suelo» solo aparece si tiene algo: SMAP listo, la estación del productor o ECOSTRESS (solo el
  // ejemplo de Durazno). Fuera de Uruguay SMAP tarda horas la primera vez: hasta entonces el grupo no se muestra.
  const hayAgua = !!smap || !!est || (esEjemplo && campo.id === "demo-durazno-1000");
  const enPlan = new Set<string>((plan?.secciones || []).flatMap((x) => x.cultivos).filter((c) => !["cobertura", "verdeo", "barbecho"].includes(c)));
  riesgos.sort(([a], [b]) => Number(enPlan.has(b)) - Number(enPlan.has(a)));
  const delPlan = riesgos.filter(([cod]) => enPlan.has(cod));
  const otrosCultivos = riesgos.filter(([cod]) => !enPlan.has(cod));
  const filaRiesgo = ([cod, r]: [string, any]) => (
    <div className={`fila ${enPlan.has(cod) ? "del-plan" : ""}`} role="row" key={cod}>
      <span role="cell"><b>{nombreCultivo(catalogo, cod, true)}</b>{enPlan.has(cod) && <em>en tu plan</em>}<small>{r.ventana_agua || r.ventana_helada || ""}</small></span>
      <span role="cell" data-r="Seca"><DiezAnios p={r.prob_seca} anios={r.anios_evaluados} /></span>
      <span role="cell" data-r="Helada"><DiezAnios p={r.prob_helada_agro} anios={r.anios_evaluados} /></span>
      <span role="cell" data-r="Calor"><DiezAnios p={r.prob_calor} anios={r.anios_evaluados} /></span>
    </div>
  );

  const cultivosEnTend = Object.keys(t.cultivos as Record<string, any>);
  const cultivosPlan = cultivosEnTend.filter((c) => enPlan.has(c));
  const codigosAMostrar = cultivosPlan.length > 0 ? cultivosPlan : cultivosEnTend;

  const cultivosAntesAhora: FilaCultivoAntesAhora[] = codigosAMostrar.map((cod) => ({
    cod,
    nombre: nombreCultivo(catalogo, cod, true),
    enPlan: enPlan.has(cod),
    seca: t.cultivos[cod]?.prob_seca,
    calor: t.cultivos[cod]?.prob_calor,
  }));

  const fraseHallazgo = calcularHallazgoFuerte(codigosAMostrar, t.cultivos, catalogo);
  const hallazgos = armarHallazgos();

  function armarHallazgos(): Hallazgo[] {
    const h: Hallazgo[] = [];
    // 1) la seca del cultivo del plan que más se corrió, solo si es un cambio claro (misma regla que el gráfico)
    const conSeca = Object.entries(t.cultivos as Record<string, any>).filter(([c, v]) => v.prob_seca && v.prob_seca.ahora != null && v.prob_seca.antes != null && (enPlan.size === 0 || enPlan.has(c)));
    conSeca.sort(([, a], [, b]) => (b.prob_seca.ahora - b.prob_seca.antes) - (a.prob_seca.ahora - a.prob_seca.antes));
    const top = conSeca[0];
    const esClaro = top && (top[1].prob_seca.cambio_claro ?? (Math.abs(top[1].prob_seca.ahora - top[1].prob_seca.antes) >= 0.2));
    if (top && esClaro) {
      const [c, v] = top;
      h.push({ texto: `${nombreCultivo(catalogo, c, true)}: en los últimos años (${t.periodo_ahora}) le faltó agua en la floración ${de10(v.prob_seca.ahora)}; en ${t.periodo_antes} eran ${de10(v.prob_seca.antes, true)}.`, destino: "datos-antes-ahora" });
    } else {
      // sin un cambio claro: el riesgo de seca de todo el período del cultivo que más ocupa el plan
      const area: Record<string, number> = {};
      for (const a of plan?.secciones || []) for (const c of a.cultivos) if (!["cobertura", "verdeo", "barbecho"].includes(c)) area[c] = (area[c] || 0) + a.area_ha;
      const principal = Object.keys(area).sort((a, b) => area[b] - area[a]).find((c) => (cl.riesgos_cultivo as Record<string, any>)[c]?.prob_seca != null);
      const r = principal ? (cl.riesgos_cultivo as Record<string, any>)[principal] : null;
      if (principal && r) {
        h.push({ texto: `${nombreCultivo(catalogo, principal, true)}: de ${cl.periodo.replace("-", " a ")} le faltó agua en el momento crítico ${de10(r.prob_seca)}.`, destino: "datos-riesgo" });
      }
    }
    h.push({ texto: `Los veranos tienen más calor fuerte: ${fmt(t.dias_calor_verano.ahora, 0)} días de más de 35 °C por verano, contra ${fmt(t.dias_calor_verano.antes, 0)} en ${t.periodo_antes}.`, destino: "datos-cifras" });
    if (Math.abs(z.anomalia_pct) >= 15) h.push({ texto: `Ahora mismo: en los últimos 90 días llovió ${fmt(Math.abs(z.anomalia_pct))} % ${z.anomalia_pct < 0 ? "menos" : "más"} que lo normal (${fmt(z.lluvia_90d_mm)} mm).`, destino: "datos-cifras" });
    const peor = [...analisis!.secciones].filter((x) => x.actual?.erosion).sort((a, b) => b.actual!.erosion.ratio - a.actual!.erosion.ratio)[0];
    if (peor && peor.actual && !peor.actual.erosion.cumple) h.push({ texto: `${peor.nombre}: con lo que se hace hoy el suelo pierde ${fmt(peor.actual.erosion.a_t_ha, 1)} t/ha por año y aguanta ${fmt(peor.actual.erosion.tolerancia_t)}: es la sección que más se lava.`, destino: "datos-secciones", seccion: peor.id });
    return h.slice(0, 4);
  }

  function ir(destino: string, seccion?: string) {
    if (seccion) setSec(seccion);
    if (destino === "datos-g-agronomo") setDatosAgronomo(true);
    irA(destino);
  }

  return (
    <div className="panel panel-datos">
      <div className="panel-titulo">
        <div>
          <h2>Clima, suelo y satélite de tu campo</h2>
          <p>Clima diario de la NASA desde {cl.periodo.split("-")[0]} en la zona de tu campo, el suelo oficial del MGAP y lo que vio el satélite en cada sección.</p>
        </div>
        <span className="fuente">Analizado el {new Date(analisis.generado).toLocaleString("es-UY", { dateStyle: "medium", timeStyle: "short" })}</span>
      </div>

      <nav className="datos-indice" aria-label="Partes de la pestaña Datos">
        {GRUPOS.filter((g) => g.id !== "datos-g-agua" || hayAgua).map((g) => (
          <button key={g.id} type="button" className="chip" onClick={() => ir(g.id)}>{g.t}</button>
        ))}
      </nav>

      {/* primero la respuesta: lo que más importa, en palabras y con el número (13-mostrar-los-datos.md) */}
      <section className="datos-grupo" id="datos-g-importa">
        <div className="caja hallazgos">
          <h3>Lo que más importa en tu campo</h3>
          <ul>
            {hallazgos.map((x, k) => (
              <li key={k}>
                <span>{x.texto}</span>{" "}
                <button type="button" className="btn texto chico ver-hallazgo" onClick={() => ir(x.destino, x.seccion)}>Ver</button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="datos-grupo" id="datos-g-clima">
        <h2 className="datos-grupo-titulo">Tu clima</h2>
        <div className="cifras" id="datos-cifras">
          <div className="cifra"><div className="rotulo">Lluvia de los últimos 90 días</div>
            <div className="valor">{fmt(u.agua(z.lluvia_90d_mm), u.decAgua)} <small>{u.uAgua}</small></div>
            <div className="nota"><span className={z.anomalia_pct < 0 ? "cambio-sube" : "cambio-baja"}>{z.anomalia_pct > 0 ? "+" : ""}{fmt(z.anomalia_pct)} %</span> contra lo normal (al {z.hasta})</div></div>
          <div className="cifra"><div className="rotulo">Lluvia media por año</div><div className="valor">{fmt(u.agua(cl.erosividad.lluvia_anual_mm), u.decAgua)} <small>{u.uAgua}</small></div>
            <div className="nota">{t.periodo_antes}: {fmt(u.agua(t.lluvia_anual.antes), u.decAgua)} · {t.periodo_ahora}: {fmt(u.agua(t.lluvia_anual.ahora), u.decAgua)}</div></div>
          <div className="cifra"><div className="rotulo">Agua que se evapora por año</div><div className="valor">{fmt(u.agua(et0Anual), u.decAgua)} <small>{u.uAgua}</small></div>
            <div className="nota">{mesesQueSeSeca(cl.mensual)}</div></div>
          <div className="cifra"><div className="rotulo">Días de más de 35 °C por verano</div><div className="valor">{fmt(t.dias_calor_verano.ahora, 1)}</div>
            <div className="nota">eran {fmt(t.dias_calor_verano.antes, 1)} en {t.periodo_antes}</div></div>
          {cl.tormentas && (
            <div className="cifra"><div className="rotulo">Lluvias fuertes (≥ 50 mm)</div>
              <div className="valor">{fmt(cl.tormentas.por_anio, 1)} <small>por año</small></div>
              <div className="nota">{`meses pico: ${cl.tormentas.meses_pico.slice(0, 2).join(" y ")} (${cl.tormentas.fuente})`}</div></div>
          )}
        </div>

        <div className="grilla-cajas">
          <div className="caja" id="datos-antes-ahora">
            <h3>Tu clima ya cambió: antes y ahora</h3>
            <p className="bajada">Compara dos períodos ({t.periodo_antes} contra {t.periodo_ahora}, datos diarios de la NASA) en el momento crítico de cada cultivo (la floración o la ventana en que más sufre por seca o calor). Con unos 17 años por período, los cambios chicos pueden ser puro azar: solo se destacan los cambios claros.</p>
            <div className={`hallazgo-clima ${fraseHallazgo.includes("No se observan") ? "" : "aviso-cambio"}`}>
              <span>{fraseHallazgo}</span>
            </div>
            <GraficoAntesAhora cultivos={cultivosAntesAhora} antes={t.periodo_antes} ahora={t.periodo_ahora} />
            <p className="fuente" style={{ marginTop: 8 }}>
              Última helada del invierno: {t.ultima_helada.antes} → {t.ultima_helada.ahora}. Primera helada del otoño: {t.primera_helada.antes} → {t.primera_helada.ahora}
              {t.primera_helada.corrimiento_dias ? ` (${t.primera_helada.corrimiento_dias > 0 ? "+" : ""}${t.primera_helada.corrimiento_dias} días)` : ""}.
            </p>
          </div>
          <div className="caja">
            <h3>Lo que llueve contra lo que se evapora, mes a mes</h3>
            <p className="bajada">Promedio {cl.periodo}. Cuando la línea queda por encima de las barras, el suelo se va secando.</p>
            <GraficoLluviaET mensual={cl.mensual} />
          </div>
          {cl.tormentas && (
            <div className="caja" id="datos-tormentas">
              <h3>Lluvias fuertes</h3>
              <p className="bajada">{`Lluvias de 50 mm o más en un día (${cl.tormentas.fuente} ${cl.tormentas.periodo}).`}</p>
              <div style={{ marginBottom: 12, fontSize: 13, lineHeight: 1.5 }}>
                <p style={{ margin: "0 0 6px" }}>
                  <strong>{`${fmt(cl.tormentas.por_anio, 1)} lluvias fuertes por año`}</strong>. Meses en que más caen: <strong>{cl.tormentas.meses_pico.join(", ")}</strong>.
                </p>
                <p style={{ margin: "0 0 6px" }}>
                  <span>
                    {cl.tormentas.cada_anios_grande != null
                      ? `Una de 100 mm cada ${fmt(cl.tormentas.cada_anios_grande, 1)} años (${cl.tormentas.grandes} en ${cl.tormentas.anios} años).`
                      : `Sin lluvias de 100 mm en los ${cl.tormentas.anios} años evaluados.`}
                  </span>{" "}
                  <span>{`La más grande: ${cl.tormentas.maxima.mm} mm el ${formatearFecha(cl.tormentas.maxima.fecha)}.`}</span>
                </p>
              </div>
              <GraficoTormentasMes por_mes={cl.tormentas.por_mes} />
              {cl.tormentas.fuente === "NASA POWER" ? (
                <p className="fuente" style={{ marginTop: 8 }}>
                  Datos de NASA POWER: promedia una celda de unos 50 km y achata las tormentas.
                </p>
              ) : (
                <p className="fuente" style={{ marginTop: 8 }}>
                  {`Datos de ${cl.tormentas.fuente} (${cl.tormentas.periodo}).`}
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="datos-grupo" id="datos-g-riesgo">
        <h2 className="datos-grupo-titulo">Qué riesgo corre cada cultivo</h2>
        <div className="caja" id="datos-riesgo">
          <h3>Cuántos años de cada 10 le va mal a cada cultivo</h3>
          <p className="bajada">Riesgo histórico de todo el período evaluado ({cl.periodo.replace("-", " a ")}, sin dividir en antes y ahora), con {`${fmt(cl.agua_util_mm)} mm de`} <Termino t="Agua útil">agua útil</Termino> en el suelo. Cada fila son 10 años: los cuadros pintados son los años en que el cultivo pasó su momento crítico con menos de la mitad del agua (seca), con <Termino t="Riesgo de helada">helada</Termino> (2 °C o menos a 2 m; a ras del cultivo suele ser más frío) o con 3 o más días de calor extremo. Primero, los cultivos de tu plan.</p>
          <div className="riesgo-diez" role="table" aria-label="Años de cada 10 con problemas, por cultivo">
            <div className="fila cab" role="row"><span role="columnheader">Cultivo</span><span role="columnheader">Seca</span><span role="columnheader">Helada</span><span role="columnheader">Calor</span></div>
            {(otrosCultivos.length && delPlan.length ? delPlan : riesgos).map(filaRiesgo)}
          </div>
          {/* Eran 16 filas (hasta el girasol que el productor excluyó); a la vista, solo los del plan */}
          {otrosCultivos.length > 0 && delPlan.length > 0 && (
            <details className="tecnico">
              <summary>{`Ver los otros ${otrosCultivos.length} cultivos`}</summary>
              <div className="riesgo-diez" role="table" aria-label="Años de cada 10 con problemas, otros cultivos">
                {otrosCultivos.map(filaRiesgo)}
              </div>
            </details>
          )}
        </div>
        <Escenario cultivos={riesgos.slice(0, 6).map(([cod]) => cod)} />
      </section>

      {hayAgua && (
        <section className="datos-grupo" id="datos-g-agua">
          <h2 className="datos-grupo-titulo">El agua en tu suelo</h2>
          <Humedad res={smap} />
          <Ecostress />
          {est && (
            <div className="caja">
              <h3>{campo.estacion?.referencia ? "Una estación cercana contra la NASA" : "Tu estación contra la NASA"}</h3>
              <p className="bajada">{est.dias_en_comun} días en común ({est.desde} a {est.hasta}).</p>
              <div className="alerta azul">{est.conclusion}</div>
            </div>
          )}
        </section>
      )}

      <section className="datos-grupo" id="datos-g-secciones">
        <h2 className="datos-grupo-titulo">Tu campo sección por sección</h2>
        <div className="caja" id="datos-secciones">
          <h3>Suelo y satélite de cada sección</h3>
          <div className="selector-seccion" style={{ margin: "8px 0 14px" }}>
            {analisis.secciones.map((x) => <button key={x.id} className={`chip ${x.id === s.id ? "on" : ""}`} onClick={() => setSec(x.id)}>{x.nombre}</button>)}
          </div>
          <div className="grilla-cajas">
            <div>
              <h3 style={{ fontSize: 14 }}>Suelo (MGAP)</h3>
              {s.suelo?.ok ? (
                <>
                  <dl className="ficha-dl" style={{ marginTop: 8 }}>
                    <dt>Suelo</dt><dd>{s.suelo.suelo_dominante}</dd>
                    <dt>Pendiente</dt><dd>{fmt(s.suelo.pendiente_pct, 1)} %</dd>
                    <dt>Agua que guarda</dt><dd>{`${fmt(s.agua_util_mm)} mm para el cultivo`} <span className="fuente">({s.agua_util_origen})</span></dd>
                    <dt>Cuánto aguanta</dt><dd>{`perder hasta ${fmt(s.suelo.tolerancia_t)} t/ha por año sin degradarse`}
                      {s.actual?.erosion ? <> · con lo de hoy pierde <b className={s.actual.erosion.cumple ? "" : "cambio-sube"}>{`${fmt(s.actual.erosion.a_t_ha, 1)} t/ha`}</b></> : null}</dd>
                  </dl>
                  <details className="tecnico">
                    <summary>Detalle técnico para el agrónomo</summary>
                    <dl className="ficha-dl">
                      <dt>Grupo CONEAT</dt><dd>{s.suelo.grupo_coneat}{s.suelo.indice_coneat ? ` · índice ${s.suelo.indice_coneat}` : ""}</dd>
                      <dt>Erodabilidad (K)</dt><dd>{fmt(s.suelo.factor_k, 3)}</dd>
                      <dt>Tolerancia (T)</dt><dd>{`${fmt(s.suelo.tolerancia_t)} t/ha/año`}</dd>
                      <dt>Factor R</dt><dd>{fmt(analisis.factor_r.usado)} ({analisis.factor_r.medido ? "medido" : `MGAP ${fmt(analisis.factor_r.mgap?.r)}`} · estimado con NASA {fmt(analisis.factor_r.nasa)})</dd>
                    </dl>
                  </details>
                </>
              ) : <div className="alerta ambar">El MGAP no respondió para esta sección; se usaron valores típicos.</div>}
              {s.analisis_suelo.alertas.map((a, i) => <div key={i} className="alerta ambar" style={{ marginTop: 8 }}>{a}</div>)}
              {s.analisis_suelo.notas.map((a, i) => <div key={i} className="fuente" style={{ marginTop: 4 }}>{a}</div>)}
            </div>
            <div>
              <h3 style={{ fontSize: 14 }}>
                {s.ndvi.hls?.ok ? "Cobertura vista desde el satélite (MODIS y HLS 30 m)" : <>Cobertura vista desde el satélite (MODIS <Termino t="NDVI (índice de verdor)">NDVI</Termino>)</>}
              </h3>
              <p className="bajada" style={{ marginTop: 4 }}>
                {s.ndvi.hls?.ok
                  ? "Verdor mensual de la sección: MODIS (250 m, un punto central) y HLS (30 m, mediana sobre todo el polígono)."
                  : "Qué tan verde se vio la sección cada mes. Un píxel de 250 m: en secciones chicas mezcla bordes."}
              </p>
              <GraficoNDVI
                serie={s.ndvi.mensual || []}
                serieHls={s.ndvi.hls?.ok ? s.ndvi.hls.mensual : undefined}
                umbrales={s.ndvi.umbrales}
                corteAuto={metodos?.ok && metodos.metodos[1].aplica ? metodos.metodos[1].corte : null}
              />
              {s.ndvi.hls?.ok && s.ndvi.hls.coincidencia_pct != null && (
                <div className="alerta verde" style={{ marginTop: 8, fontSize: 12 }}>
                  <div>
                    <b>Coincidencia entre MODIS y HLS:</b> {s.ndvi.hls.coincidencia_pct} %
                    {s.ndvi.hls.correlacion != null && (
                      <> · <span>correlación</span> r = {s.ndvi.hls.correlacion.toFixed(2).replace(".", ",")} · <span>diferencia media</span> {s.ndvi.hls.dif_media?.toFixed(2).replace(".", ",")}</>
                    )}
                  </div>
                  <div style={{ marginTop: 2, fontSize: 11.5, opacity: 0.9 }}>
                    HLS promedia todo el polígono a 30 m (Landsat + Sentinel-2); MODIS mira un punto de 250 m.
                  </div>
                </div>
              )}
              {s.ndvi.hls && !s.ndvi.hls.ok && (
                <div className="fuente" style={{ marginTop: 6 }}>
                  HLS a 30 m no estuvo disponible. Se muestra solo MODIS.
                </div>
              )}
              {!!s.ndvi.temporadas?.length && (
                <table className="tabla-mini" style={{ marginTop: 8 }}>
                  <thead><tr><th>Temporada</th><th>NDVI máx.</th><th>Lo que se ve</th></tr></thead>
                  <tbody>{s.ndvi.temporadas.slice(-6).map((x) => <tr key={x.temporada}><td>{x.temporada}</td><td>{x.ndvi_max.toFixed(2).replace(".", ",")}</td><td>{x.uso_detectado}</td></tr>)}</tbody>
                </table>
              )}
              <MetodosDescubierto res={metodos} />
            </div>
          </div>
        </div>
        <RelieveDatos />
      </section>

      {/* La historia, como evidencia (antes «Cómo le habría ido a este plan», en el Plan) */}
      <section className="datos-grupo" id="datos-g-creer">
        <h2 className="datos-grupo-titulo">¿Le podemos creer a la app?</h2>
        <CreerleALaApp />
      </section>

      <section className="datos-grupo" id="datos-g-agronomo">
        <details className="datos-agronomo" open={datosAgronomo} onToggle={(e) => setDatosAgronomo((e.currentTarget as HTMLDetailsElement).open)}>
          <summary>
            <span className="datos-grupo-titulo">Para el agrónomo</span>
            <span className="bajada">Qué quiere decir cada término, satélite contra estación, los límites de estos datos y las fuentes.</span>
          </summary>
          <Glosario />
          <div className="caja">
            <h3>Límites de estos datos</h3>
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, color: "var(--texto-2)", fontSize: 13 }}>
              {cl.limites.map((l: string, i: number) => <li key={i}>{l}</li>)}
              <li>El NDVI de MODIS es un píxel de 250 m (6,25 ha); HLS (30 m) es el próximo paso, con cuenta de Earthdata.</li>
              <li>La erosión usa la ecuación del Plan de Uso y las relaciones de pérdida de suelo de Erosión 6.0 (MGAP - UdelaR).</li>
            </ul>
            <h3 style={{ marginTop: 14 }}>Fuentes</h3>
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13 }}>
              {analisis.fuentes.map((f) => <li key={f.nombre}><a href={f.url} target="_blank" rel="noreferrer">{f.nombre}</a> <span className="fuente">— {f.uso}</span></li>)}
            </ul>
          </div>
        </details>
      </section>
    </div>
  );
}
