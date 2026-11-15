import { etiquetaCortaTemporada } from "./eleccion";
import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { colorCultivo, nombreCorto, nombreCultivo, useApp } from "../store";
import { PlanoSVG } from "./PlanoSVG";
import { PlanoAjustado } from "./PlanoAjustado";
import { IconoCultivo } from "../comun/Cultivo";
import { Informe } from "./Informe";
import { CreerEnPlan } from "./CreerEnPlan";
import { ResumenEleccion } from "./ResumenEleccion";
import { ElegirLote } from "./ElegirLote";
import { ParaElAgronomo } from "./ParaElAgronomo";
import { ProximoAnio } from "./ProximoAnio";

import { descargarPlano } from "./descargarPlano";
import { Cargando } from "../comun/Cargando";

// la maqueta 3D (three.js) se baja recién cuando se pide
const Vista3D = lazy(() => import("../relieve/Vista3D").then((m) => ({ default: m.Vista3D })));

/** El calendario se desplaza al costado si no entran las temporadas: mientras quede algo a la derecha, el borde se
 * desvanece en vez de cortar una columna a la mitad.
 *
 * La temporada elegida se marca con un solo marco alrededor de toda la columna, que se desliza al tocar otra. */
function MarcoCalendario({ sel, children }: { sel: number; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [sigue, setSigue] = useState(false);
  const [marco, setMarco] = useState<{ x: number; y: number; w: number; h: number; recorte: number } | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const medir = () => {
      setSigue(el.scrollWidth - el.clientWidth - el.scrollLeft > 4);
      const ths = el.querySelectorAll<HTMLElement>("thead th");
      const th = ths[sel + 1];
      const tabla = el.querySelector("table");
      if (!th || !tabla) { setMarco(null); return; }
      const base = el.getBoundingClientRect();
      const a = th.getBoundingClientRect();
      const t = tabla.getBoundingClientRect();
      // el marco va encima de la tabla: se recorta solo lo que queda debajo de esa columna
      const fija = ths[0].getBoundingClientRect().right;
      const recorte = Math.max(0, fija - (a.left - 3));
      // en coordenadas del contenido que se desplaza, así el marco viaja con la tabla
      setMarco({ x: a.left - base.left + el.scrollLeft, y: a.top - base.top, w: a.width, h: t.bottom - a.top - 3, recorte });
    };
    medir();
    el.addEventListener("scroll", medir, { passive: true });
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    const tabla = el.querySelector("table");
    if (tabla) ro.observe(tabla);
    return () => { el.removeEventListener("scroll", medir); ro.disconnect(); };
  }, [sel]);
  return (
    <div ref={ref} className={`calendario-marco ${sigue ? "sigue" : ""}`}>
      {marco && (
        <div className="calendario-columna-sel" aria-hidden
          style={{ transform: `translate(${marco.x - 3}px, ${marco.y - 3}px)`, width: marco.w + 6, height: marco.h + 6,
            clipPath: marco.recorte > 0 ? `inset(-2px -2px -2px ${marco.recorte}px)` : undefined }} />
      )}
      {children}
    </div>
  );
}

function fmt(n: number, d = 0) {
  return n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

function unirNombres(arr: string[]): string {
  if (arr.length === 0) return "";
  if (arr.length === 1) return arr[0];
  const ult = arr[arr.length - 1];
  const empiezaI = /^[ií](?![aeouáéóú])/i.test(ult) || /^hi(?![aeouáéóú])/i.test(ult);
  const conj = empiezaI ? " e " : " y ";
  return arr.slice(0, -1).join(", ") + conj + ult;
}

export function Plan() {
  const { plan, campo, catalogo, temporada, setTemporada, seccionSel, seccionAuto, setSeccionSel, setSeccionAuto, analisis, mapaPlan3D, setMapaPlan3D } = useApp();
  //
  // al lado del mapa, primero el plan del próximo año; todo lo demás, en «Detalle»
  const [vista, setVista] = useState<"proximo" | "detalle">("proximo");
  // si la persona toca un lote (en el plano o en la tabla), se abren sus opciones en «Detalle»
  const seccionPrevia = useRef(seccionSel);
  useEffect(() => {
    if (seccionSel && seccionSel !== seccionPrevia.current && !seccionAuto) setVista("detalle");
    seccionPrevia.current = seccionSel;
  }, [seccionSel, seccionAuto]);
  const tocarLote = (id: string) => {
    setSeccionSel(id);
    setVista("detalle");
  };
  // el recuadro del mapa (con sus temporadas) en pantalla completa; sirve sobre todo para la maqueta 3D, que en el
  // recuadro queda chica
  const [grande, setGrande] = useState(false);
  useEffect(() => {
    if (!grande) return;
    const alTecla = (e: KeyboardEvent) => { if (e.key === "Escape") setGrande(false); };
    window.addEventListener("keydown", alTecla);
    return () => window.removeEventListener("keydown", alTecla);
  }, [grande]);
  // «Reproducir» (pasar las temporadas solas) se sacó
  const [informe, setInforme] = useState(false);
  const [descargando, setDescargando] = useState(false);
  // Se sacó la tira de temporadas con su arrastre; las temporadas se eligen con las miniaturas debajo del plano

  // siempre hay un lote tocado al entrar: el primero de la lista (el de más a la izquierda), igual que en Comparar.
  // Antes era el más grande
  useEffect(() => {
    if (!plan || !analisis?.secciones?.length) return;
    if (!seccionSel || !analisis.secciones.some((s) => s.id === seccionSel)) {
      const primero = analisis.secciones[0];
      if (primero) setSeccionAuto(primero.id);
    }
  }, [plan, analisis, seccionSel, setSeccionAuto]);

  useEffect(() => {
    if (plan && temporada >= plan.temporadas.length) setTemporada(plan.temporadas.length - 1);
  }, [plan, temporada, setTemporada]);

  const info = useMemo(() => (cod: string) => {
    const c = catalogo?.cultivos.find((x) => x.codigo === cod);
    return { color: c?.color || "#999", icono: c?.icono || "barbecho", nombre: c?.nombre || cod };
  }, [catalogo]);

  if (!plan || !campo.contorno) {
    return (
      <div className="vacio"><div className="caja">
        <h3>Todavía no hay plan</h3>
        <p>Cuando termine la entrevista y el análisis, acá vas a ver tu campo pintado con las opciones para cada sección, temporada por temporada, para revisar y ajustar.</p>
      </div></div>
    );
  }

  // si el plan quedó más corto que la temporada elegida, se ve la última
  const ti = Math.min(temporada, plan.temporadas.length - 1);
  const t = plan.temporadas[ti];
  const resumen = plan.resumen_temporadas[ti];
  const cultivoDe = (i: number) => (sid: string) => plan.secciones.find((a) => a.seccion_id === sid)?.cultivos[i];
  const total = campo.secciones.reduce((a, s) => a + (s.area_ha || 0), 0) || 1;
  const totalCampo = campo.area_ha || 0;
  const haFuera = totalCampo > total && totalCampo - total >= 0.5
    ? Math.round((totalCampo - total) * 10) / 10
    : 0;
  const haFueraStr = haFuera % 1 === 0 ? fmt(haFuera, 0) : fmt(haFuera, 1);

  const sinCubrir = plan.secciones.filter((s) => s.cultivos[ti] === "barbecho");
  const haSinCubrir = Math.round(sinCubrir.reduce((acc, s) => acc + (s.area_ha || 0), 0) * 10) / 10;
  const haSinCubrirStr = haSinCubrir % 1 === 0 ? fmt(haSinCubrir, 0) : fmt(haSinCubrir, 1);
  const nombresSinCubrir = Array.from(new Set(sinCubrir.map((s) => s.seccion || s.seccion_id)));
  const lotesSinCubrir = unirNombres(nombresSinCubrir);

  async function alDescargarPlano() {
    if (!plan || !campo.contorno || descargando) return;
    setDescargando(true);
    try {
      await descargarPlano(campo, plan, catalogo, analisis);
    } catch (err) {
      console.error("Error al descargar plano:", err);
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="panel panel-plan">
      {informe && <Informe onCerrar={() => setInforme(false)} />}
      <div className="plan-layout">
        {grande && <div className="plan-mapa-telon no-imprimir" onClick={() => setGrande(false)} aria-hidden />}
        <div className={`plan-col-mapa no-imprimir ${grande ? "grande" : ""}`}>
          {/* Los controles van en una franja arriba del plano, no encima (tapaban rótulos) */}
          <div className="plan-vista-barra">
            {/* Era una pastilla
                blanca «2D | 3D» de 12 px que se perdía sobre la foto; ahora es oscura como el notch, con ícono y
                nombre, y en 2D el botón del 3D brilla un par de veces al abrir el Plan */}
            <div className="mapa-plan-modo" role="radiogroup" aria-label="Cómo ver el campo">
              <button type="button" role="radio" aria-checked={!mapaPlan3D} className={!mapaPlan3D ? "on" : ""} onClick={() => setMapaPlan3D(false)} title="Plano del campo con el cultivo de cada lote">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M4 4h16v16H4z" /><path d="M4 12h9V4M13 12l7 5" /></svg>
                <span>Plano</span>
              </button>
              <button type="button" role="radio" aria-checked={mapaPlan3D} className={`modo-3d ${mapaPlan3D ? "on" : ""}`} onClick={() => setMapaPlan3D(true)} title="Maqueta del campo con el relieve real de la NASA">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m2 20 7-12 4 6.5L16 10l6 10H2Z" /><path d="m7.2 11.2 1.8 1.3 1.6-1.4" /></svg>
                <span>Relieve 3D</span>
              </button>
            </div>
            <button type="button" className="mapa-plan-agrandar" onClick={() => setGrande(!grande)} aria-label={grande ? "Volver al tamaño normal" : "Ver en pantalla completa"} title={grande ? "Volver al tamaño normal (Esc)" : "Ver en pantalla completa"}>
              {grande ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" /></svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" /></svg>
              )}
            </button>
          </div>
          <div className="mapa-plan">
            {mapaPlan3D ? (
              <Suspense fallback={<div className="vista3d-cargando"><Cargando que="calculando" size={32} etiqueta="Cargando vista 3D" /><span>Cargando vista 3D…</span></div>}>
                <Vista3D grande={grande} />
              </Suspense>
            ) : (
              <PlanoAjustado contorno={campo.contorno} secciones={campo.secciones} cultivoDe={cultivoDe(temporada)} info={info}
                seleccion={seccionSel} onSeccion={setSeccionSel} />
            )}
          </div>
          {/* Las temporadas, como miniaturas del plano (antes una tira con barra de desplazamiento arriba
              del mapa y las miniaturas abajo de todo de la página) */}
          <div className="temporadas-mini" role="radiogroup" aria-label="Temporada que se ve en el plano">
            {plan.temporadas.map((x, i) => (
              <button key={i} type="button" role="radio" aria-checked={i === temporada} className={`temporada-mini ${i === temporada ? "on" : ""}`}
                onClick={() => setTemporada(i)} title={x.etiqueta}>
                <PlanoSVG contorno={campo.contorno!} secciones={campo.secciones} cultivoDe={cultivoDe(i)} info={info} W={120} H={84} etiquetas={false} />
                <span className="t">{etiquetaCortaTemporada(x)}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="plan-col-info">
          {/* «Revisar mis datos» se sacó porque Datos tiene su propia parte. «Tu plan»
              ya no se ve, porque el notch dice «Plan»; los botones suben al hueco junto al notch */}
          <div className="plan-titulo">
            <div className="plan-titulo-fila">
              <h2 className="solo-lectores">Tu plan</h2>
              <div className="fila no-imprimir plan-acciones">
                <button className="btn" onClick={alDescargarPlano} disabled={descargando}>
                  {descargando ? "Descargando plano…" : "Descargar plano"}
                </button>
                <button className="btn primario" onClick={() => setInforme(true)}>Informe para el agrónomo</button>
              </div>
            </div>
            <div className="segmentado plan-vistas no-imprimir" role="tablist" aria-label="Qué ver del plan">
              <button type="button" role="tab" aria-selected={vista === "proximo"} className={vista === "proximo" ? "on" : ""} onClick={() => setVista("proximo")}>Próximo año</button>
              <button type="button" role="tab" aria-selected={vista === "detalle"} className={vista === "detalle" ? "on" : ""} onClick={() => setVista("detalle")}>Detalle</button>
            </div>
          </div>

          {vista === "proximo" && (
            <>
              <ProximoAnio alTocarLote={tocarLote} />
              <div>
              {/* La charla de IEEE pide que se note qué es demostración; el padrón es real y el dueño no es este */}
              {campo.id === "demo-durazno-1000" && (
                <div className="alerta azul" style={{ marginTop: 8 }}>Campo de ejemplo: el padrón, el suelo, el clima y lo que vio el satélite son reales; el productor y sus respuestas son inventados para la demostración y no describen al dueño real.</div>
              )}
              {campo.id === "demo-iowa-madison" && (
                <div className="alerta azul" style={{ marginTop: 8 }}>Campo de ejemplo en Iowa: el contorno sale del Cropland Data Layer del USDA y el suelo (SSURGO), el clima y lo que vio el satélite son reales; el productor y sus respuestas son inventados para la demostración.</div>
              )}
              {campo.id?.startsWith("ejemplo-") && (
                <div className="alerta azul" style={{ marginTop: 8 }}>Campo de ejemplo: el lugar, el suelo, el clima, el relieve y lo que vio el satélite son reales; el productor y sus respuestas son inventados para la demostración.</div>
              )}
              {haFuera > 0 && (
                <p className="plan-fuera-lotes">
                  {`${haFueraStr} ha quedaron fuera de los lotes (caminos, casco, monte) y no entran en el plan.`}
                </p>
              )}
              </div>
            </>
          )}

          {vista === "detalle" && (
          <>
          <p className="bajada plan-detalle-intro">Arranca en la opción sugerida para cada lote. Tocá un lote en el plano para ver las otras opciones, con su porqué, y elegí vos qué probar. Debajo del plano, tocá una temporada para verla.</p>
          {/* primero el lote tocado, con sus opciones: es a lo que se llega tocando un lote en el plano o en la tabla */}
          {seccionSel ? <ElegirLote seccionId={seccionSel} /> : (
            <div className="alerta azul">Tocá un lote del plano para ver sus alternativas y elegir.</div>
          )}
          <ResumenEleccion />

          <div className="caja">
            {/* «suelo cubierto» era una tarjeta suelta que decía poco; ahora es una línea a la
                derecha del título de la temporada. Se fue «ha equivalentes de forraje», que no se entendía */}
            <div className="caja-temporada-cabeza">
              <h3>{t.etiqueta}</h3>
              {haSinCubrir === 0 ? (
                <span className="temporada-cubierto bien">Todo el campo cubierto</span>
              ) : (
                <span className="temporada-cubierto mal">
                  {lotesSinCubrir ? `${haSinCubrirStr} ha sin cubrir (${lotesSinCubrir})` : `${haSinCubrirStr} ha sin cubrir`}
                </span>
              )}
            </div>
            <p className="bajada">Superficie por cultivo en esta temporada</p>
            <div className="leyenda">
              {Object.entries(resumen.area_por_cultivo).map(([cod, ha]) => (
                <div key={cod} className="leyenda-item">
                  <svg width="30" height="18"><rect width="30" height="18" rx="4" fill={`url(#trama-${cod})`} /></svg>
                  <span style={{ display: "flex", gap: 6, alignItems: "center" }}><IconoCultivo icono={info(cod).icono} color={info(cod).color} size={16} />{nombreCorto(cod)}</span>
                  <small>{`${fmt(ha)} ha · ${fmt((100 * ha) / total)} %`}</small>
                </div>
              ))}
            </div>
          </div>

          <CreerEnPlan />

          <div className="caja">
            <h3>Calendario por sección</h3>
            <p className="bajada">Cada columna es una temporada; cada fila, una sección. Tocá una celda para ver esa temporada en el plano.</p>
            <MarcoCalendario sel={ti}>
              <table className="calendario">
                <colgroup><col className="col-seccion" />{plan.temporadas.map((_, i) => <col key={i} />)}</colgroup>
                <thead>
                  <tr><th>Sección</th>{plan.temporadas.map((x, i) => <th key={i} className={`temp ${i === temporada ? "sel" : ""}`} style={{ cursor: "pointer" }} onClick={() => setTemporada(i)}>{x.tipo === "verano" ? "Ver." : "Inv."} {x.tipo === "verano" ? `${String(x.anio).slice(2)}/${String(x.anio + 1).slice(2)}` : x.anio}</th>)}</tr>
                </thead>
                <tbody>
                  {plan.secciones.map((a) => (
                    <tr key={a.seccion_id}>
                      <th style={{ cursor: "pointer" }} onClick={() => setSeccionSel(a.seccion_id)}>{a.seccion}<br /><small className="calendario-rotacion" title={a.rotacion}>{a.rotacion}</small>{a.proxima_siembra && <small className="calendario-siembra">{a.proxima_siembra}</small>}</th>
                      {a.cultivos.map((c, i) => (
                        <td key={i} className={`celda ${i === temporada ? "sel" : ""}`} style={{ background: colorCultivo(catalogo, c) }}
                          onClick={() => { setTemporada(i); setSeccionSel(a.seccion_id); }} title={`${a.seccion} · ${plan.temporadas[i].etiqueta}: ${nombreCultivo(catalogo, c)}`}>
                          {nombreCorto(c)}
                          {a.siembras?.[i] && <span className="celda-siembra">{a.siembras[i] === "renovación" ? "se renueva" : "se siembra"}</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </MarcoCalendario>
          </div>

          <ParaElAgronomo />
          </>
          )}
        </div>
      </div>

    </div>
  );
}
