import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { colorCultivo, nombreCorto, nombreCultivo, useApp } from "../store";
import type { Campo, Catalogo, Evaluacion, Geo, Plan, SeccionAnalizada } from "../tipos";
import { fuenteLluvia } from "../comun/fuenteLluvia";
import { useUS } from "../i18n/region";
import { HA_A_AC, T_HA_A_T_AC, medidas } from "../i18n/unidades";
import "./informe.css";

/** En EE. UU. las cifras que van sin su unidad al lado (tablas, indicadores) se convierten acá: acres,
 * toneladas cortas por acre (la tolerancia T del NRCS es un entero) y pulgadas. Lo que lleva la unidad en el mismo
 * texto lo convierte la pantalla (i18n/unidades.ts). */
function unidadesInforme(us: boolean) {
  return {
    sup: (ha: number) => (us ? ha * HA_A_AC : ha), uSup: us ? "ac" : "ha",
    eros: (t: number) => (us ? t * T_HA_A_T_AC : t), uEros: us ? "t/ac/año" : "t/ha/año",
    tol: (t: number) => (us ? Math.round(t * T_HA_A_T_AC) : t),
  };
}

// Informe para llevarle al ingeniero agrónomo: primero un resumen de
// una hoja (números clave, mapa del plan, lo que contó el productor y qué se hace en cada sección), después el
// calendario del plan y el clima, una tarjeta por sección y al final el método y las fuentes. Se imprime o se
// guarda en PDF desde el navegador (A4).

function fmt(n: number | null | undefined, d = 0) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

const PRIORIDAD: Record<string, string> = {
  ingreso: "Ingreso", agua: "Riesgo de seca", suelo: "Cuidar el suelo", clima: "Helada y calor", forraje: "Forraje",
  simplicidad: "Simplicidad", diversificacion: "Diversificación",
};
const PROBLEMA: Record<string, string> = {
  anegamiento: "se anega", helada: "hiela fuerte", erosion: "se lava", suelo_superficial: "suelo superficial",
  sequia: "se seca rápido", malezas: "malezas resistentes", compactacion: "compactación",
};

function si(v: boolean | null | undefined) {
  return v === true ? "sí" : v === false ? "no" : "no informado";
}

/** Lo que se hace hoy, legible: «Barbecho / Soja 1ª» o «Trigo / Soja 2ª → Cobertura / Maíz 1ª». */
function hoyTexto(s: SeccionAnalizada): string {
  const anios = s.actual?.anios || [];
  if (!anios.length) return "—";
  if (anios.every(([a, b]) => a === anios[0][0] && b === anios[0][0])) return `${nombreCorto(anios[0][0])} (todo el año)`;
  return anios.map((par) => par.map(nombreCorto).join(" / ")).join(" → ");
}

function nombreOpcion(e: Evaluacion, s: SeccionAnalizada) {
  return e.es_actual ? `Hoy: ${hoyTexto(s)}` : e.nombre;
}

/** En la columna «En el plan»: si sigue lo de hoy no se repiten los cultivos. */
function nombreEnPlan(e: Evaluacion) {
  return e.es_actual ? "Seguir como hoy" : e.nombre;
}

function textoClaro(hex: string) {
  const h = hex.replace("#", "");
  if (h.length < 6) return true;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 150;
}

// ------------------------------------------------------------------ mapa del campo (SVG, vectorial al imprimir)
function anillos(g: Geo): number[][][] {
  return g.type === "MultiPolygon" ? g.coordinates.flat() : g.coordinates;
}

function MapaCampo({ campo, relleno, resaltar, etiquetas, ancho, alto }: {
  campo: Campo; relleno: (id: string) => string; resaltar?: string; etiquetas?: boolean; ancho: number; alto: number;
}) {
  const geo = useMemo(() => {
    const secs = campo.secciones.filter((s) => s.geometria);
    const pts = secs.flatMap((s) => anillos(s.geometria).flat());
    if (!pts.length) return null;
    const lat0 = pts.reduce((a, p) => a + p[1], 0) / pts.length;
    const kx = Math.cos((lat0 * Math.PI) / 180);
    const xs = pts.map((p) => p[0] * kx);
    const ys = pts.map((p) => p[1]);
    return { secs, kx, x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
  }, [campo.secciones]);
  if (!geo) return null;
  const pad = 8;
  const esc = Math.min((ancho - 2 * pad) / (geo.x1 - geo.x0 || 1), (alto - 2 * pad) / (geo.y1 - geo.y0 || 1));
  const ox = pad + (ancho - 2 * pad - (geo.x1 - geo.x0) * esc) / 2;
  const oy = pad + (alto - 2 * pad - (geo.y1 - geo.y0) * esc) / 2;
  const P = (p: number[]) => [ox + (p[0] * geo.kx - geo.x0) * esc, oy + (geo.y1 - p[1]) * esc];
  return (
    <svg viewBox={`0 0 ${ancho} ${alto}`} width={ancho} height={alto} className="inf-mapa" aria-hidden>
      {geo.secs.map((s) => {
        const d = anillos(s.geometria).map((r) => "M" + r.map((p) => P(p).map((v) => v.toFixed(1)).join(",")).join(" L") + "Z").join(" ");
        const op = !resaltar || resaltar === s.id ? 1 : 0.18;
        return <path key={s.id} d={d} fill={relleno(s.id)} fillOpacity={op} fillRule="evenodd" stroke="#1b1c14" strokeWidth={resaltar === s.id ? 1.6 : 0.8} />;
      })}
      {etiquetas && geo.secs.map((s) => {
        const pts = anillos(s.geometria).flat().map(P);
        const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
        const cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
        return <text key={s.id} x={cx} y={cy} className="inf-rotulo">{s.nombre}</text>;
      })}
    </svg>
  );
}

// ------------------------------------------------------------------ piezas
function Leyenda({ plan, catalogo }: { plan: Plan; catalogo: Catalogo | null }) {
  const usados: string[] = [];
  plan.secciones.forEach((a) => a.cultivos.forEach((c) => { if (!usados.includes(c)) usados.push(c); }));
  return (
    <div className="inf-leyenda">
      {usados.map((c) => <span key={c}><i style={{ background: colorCultivo(catalogo, c) }} />{nombreCorto(c)}</span>)}
    </div>
  );
}

function Calendario({ plan, catalogo }: { plan: Plan; catalogo: Catalogo | null }) {
  // en EE. UU. los acres salen del área con decimales, igual que en la tarjeta de cada sección
  const u = unidadesInforme(useUS());
  return (
    <table className="inf-calendario">
      <thead>
        <tr>
          <th />
          {plan.temporadas.map((t, i) => (
            <th key={i} className={t.tipo === "invierno" ? "inv" : ""}>{t.etiqueta.replace("Invierno", "Inv.").replace("Verano", "Ver.")}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {plan.secciones.map((a) => (
          <tr key={a.seccion_id}>
            <th className="sec">{a.seccion}<small>{`${fmt(u.sup(a.area_ha))} ${u.uSup}`}</small></th>
            {a.cultivos.slice(0, plan.temporadas.length).map((c, i) => {
              const col = colorCultivo(catalogo, c);
              return <td key={i} style={{ background: col, color: textoClaro(col) ? "#1b1c14" : "#fff" }}>{nombreCorto(c)}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Lista({ xs, max }: { xs: string[] | undefined; max: number }) {
  const v = (xs || []).slice(0, max);
  return <>{v.length ? v.map((x, i) => <li key={i}>{x}</li>) : <li className="inf-vacio">—</li>}</>;
}

function TarjetaSeccion({ s, enPlan, sugerida, relleno }: {
  s: SeccionAnalizada; enPlan: Evaluacion; sugerida: Evaluacion | null; relleno: (id: string) => string;
}) {
  const { campo } = useApp();
  const us = useUS();
  const u = unidadesInforme(us);
  const ops = [s.actual, ...s.alternativas].filter(Boolean) as Evaluacion[];
  const su = s.suelo || {};
  const tol = su.tolerancia_t ?? enPlan.erosion.tolerancia_t;
  const maxE = Math.max(...ops.map((o) => o.erosion.a_t_ha), tol) * 1.08 || 1;
  const ex = (sugerida || enPlan).explicacion;
  const chips = [
    ...(us ? [] : [`CONEAT ${su.grupo_coneat || "—"}`]), `pendiente ${fmt(su.pendiente_pct, 1)} %`, `tolerancia ${fmt(tol)} t/ha/año`,
    `agua útil ${fmt(s.agua_util_mm)} mm`, `K ${fmt(su.factor_k, 3)}`,
  ];
  return (
    <section className="inf-tarjeta">
      <div className="inf-tarjeta-cab">
        <div className="inf-mini"><MapaCampo campo={campo} relleno={relleno} resaltar={s.id} ancho={120} alto={90} /></div>
        <div>
          <p className="inf-kicker">Sección</p>
          <h3>{s.nombre} <span>{`${fmt(s.area_ha, 1)} ha`}</span></h3>
          <p className="inf-propuesta">
            Hoy: {hoyTexto(s)}
            {enPlan.es_actual ? <> · <b>en el plan sigue igual</b></> : <> → En el plan: <b>{enPlan.nombre}</b></>}
            {sugerida && sugerida.id !== enPlan.id ? <> · sugerida por el análisis: <b>{nombreEnPlan(sugerida)}</b></> : null}
          </p>
          <div className="inf-chips">
            {chips.map((c) => <span key={c}>{c}</span>)}
            {s.problemas.map((p) => <span key={p} className="alerta">{PROBLEMA[p] || p}</span>)}
          </div>
        </div>
      </div>
      <table className="inf-opciones">
        <thead><tr><th>Opción</th><th>Puntaje</th><th>Erosión <small>│ = tolerancia</small></th><th>{u.uEros}</th><th>Seca <small>años de cada 10</small></th></tr></thead>
        <tbody>
          {ops.map((o) => (
            <tr key={o.id} className={o.id === enPlan.id ? "en-plan" : ""}>
              <td className="nom">
                {nombreOpcion(o, s)}
                {o.id === enPlan.id && <em>en el plan</em>}
                {sugerida && o.id === sugerida.id && o.id !== enPlan.id && <em className="sug">sugerida</em>}
              </td>
              <td className="pts">{fmt(o.puntaje_total)}</td>
              <td className="barra">
                <div className={`bar ${o.erosion.cumple ? "ok" : "mal"}`} style={{ width: `${(100 * o.erosion.a_t_ha) / maxE}%` }} />
                <span className="tol" style={{ left: `${(100 * tol) / maxE}%` }} />
              </td>
              <td className="num">{fmt(u.eros(o.erosion.a_t_ha), 1)}</td>
              <td className="num">{fmt(10 * o.riesgo.seca, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ex && (
        <div className="inf-tres">
          <div><h4>Por qué</h4><ul><Lista xs={ex.por_que} max={2} /><Lista xs={ex.beneficios} max={2} /></ul></div>
          <div><h4>Riesgos a mirar</h4><ul><Lista xs={ex.riesgos} max={3} /></ul></div>
          <div><h4>Falta saber</h4><ul><Lista xs={ex.huecos} max={3} /></ul></div>
        </div>
      )}
    </section>
  );
}

const AVISO =
  "Esto no es un Plan de Uso. El Plan de Uso y Manejo Responsable de Suelos lo presenta un ingeniero agrónomo acreditado " +
  "ante el MGAP y lo firma el dueño de la tierra, que es responsable de cumplirlo aunque el campo esté arrendado. Este " +
  "informe sirve para preparar esa conversación. La erosión se calculó con la misma ecuación y los datos oficiales del " +
  "MGAP. Para el Plan de Uso hay que calcularla con el programa oficial, que usa el agrónomo acreditado.";

// en la hoja 1 va corto, para que el resumen entre en una página también en inglés; el completo, al final
const AVISO_CORTO =
  "Esto no es un Plan de Uso: sirve para preparar la conversación con el ingeniero agrónomo acreditado, que lo presenta " +
  "ante el MGAP. El detalle está al final del informe.";

export function Informe({ onCerrar }: { onCerrar: () => void }) {
  const { campo, analisis, plan, catalogo } = useApp();
  useEffect(() => {
    document.body.classList.add("con-informe");
    function alTecla(e: KeyboardEvent) {
      if (e.key === "Escape") onCerrar();
    }
    window.addEventListener("keydown", alTecla);
    return () => {
      document.body.classList.remove("con-informe");
      window.removeEventListener("keydown", alTecla);
    };
  }, [onCerrar]);
  if (!analisis || !plan) return null;

  const asig = new Map(plan.secciones.map((a) => [a.seccion_id, a]));
  const opcionesDe = (s: SeccionAnalizada) => [s.actual, ...s.alternativas].filter(Boolean) as Evaluacion[];
  const enPlanDe = (s: SeccionAnalizada) => {
    const ops = opcionesDe(s);
    const rid = asig.get(s.id)?.rotacion_id;
    return ops.find((o) => o.id === rid) || (rid === "actual" ? ops.find((o) => o.es_actual) : undefined) || ops[0];
  };
  const sugeridaDe = (s: SeccionAnalizada) => {
    const id = asig.get(s.id)?.sugerida_id ?? s.recomendada_id;
    const ops = opcionesDe(s);
    return ops.find((o) => o.id === id) || (id === "actual" ? ops.find((o) => o.es_actual) : undefined) || null;
  };
  const relleno = (id: string) => {
    const c = asig.get(id)?.cultivos[0];
    return c ? colorCultivo(catalogo, c) : "#ddd";
  };

  const sis = campo.sistema || {};
  const exp = campo.experiencia;
  const pr = Object.entries(analisis.prioridades || {}).filter(([, v]) => (v as number) > 0).sort((a, b) => (b[1] as number) - (a[1] as number));
  const cl = analisis.clima || {};
  const t = cl.tendencia;
  const fecha = new Date(analisis.generado).toLocaleDateString("es-UY");
  const area = campo.area_ha || campo.secciones.reduce((a, s) => a + (s.area_ha || 0), 0);
  const ub = campo.ubicacion;
  const lugar = [ub?.departamento ? ub.departamento.charAt(0) + ub.departamento.slice(1).toLowerCase() : null, ub?.padron ? `padrón ${ub.padron}` : null].filter(Boolean).join(" · ");
  const superaHoy = analisis.secciones.filter((s) => s.actual && !s.actual.erosion.cumple).length;
  const superaPlan = analisis.secciones.filter((s) => !enPlanDe(s).erosion.cumple).length;
  const baja = plan.erosion_media_actual ? (100 * (plan.erosion_media_plan - plan.erosion_media_actual)) / plan.erosion_media_actual : 0;
  const us = useUS();
  const u = unidadesInforme(us);
  const ua = medidas(us);
  const haySugerida = plan.erosion_media_sugerida != null && Math.abs(plan.erosion_media_sugerida - plan.erosion_media_plan) > 0.05;

  const acciones = (
    <div className="informe-acciones no-imprimir">
      <button className="btn primario" onClick={() => window.print()}>Guardar en PDF</button>
      <button className="btn" onClick={onCerrar}>Cerrar</button>
    </div>
  );

  return createPortal(
    <div className="informe inf" role="dialog" aria-label="Informe para el agrónomo">
      {acciones}

      {/* -------- hoja 1: el resumen */}
      <div className="inf-hoja">
        <header className="inf-banda">
          <span className="inf-marca">
            <svg width="20" height="20" viewBox="0 0 64 64" aria-hidden>
              <path d="M8 46 L56 46" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
              <path d="M13 37 Q32 16 51 37" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
              <circle cx="45" cy="15" r="6" fill="currentColor" />
            </svg>
            Seasons Ahead
          </span>
          <span className="inf-mono">INFORME PARA EL AGRÓNOMO · {fecha}</span>
        </header>
        <h1>{campo.nombre || "Campo"}</h1>
        <p className="inf-sub">{`${fmt(area)} ha`} · {analisis.secciones.length} secciones{lugar ? ` · ${lugar}` : ""}</p>

        <div className="inf-kpis">
          <div className="inf-kpi destacado">
            <span className="inf-mono">EROSIÓN MEDIA</span>
            <b>{fmt(u.eros(plan.erosion_media_actual), 1)} → {fmt(u.eros(plan.erosion_media_plan), 1)}</b>
            <small>{`${u.uEros} ·`} {fmt(baja)} % con el plan{haySugerida ? ` (con lo sugerido: ${fmt(u.eros(plan.erosion_media_sugerida!), 1)})` : ""}</small>
          </div>
          <div className="inf-kpi">
            <span className="inf-mono">SUPERAN LA TOLERANCIA</span>
            <b>{superaHoy} → {superaPlan}</b>
            <small>secciones, hoy y con el plan</small>
          </div>
          <div className="inf-kpi">
            <span className="inf-mono">CLIMA ANALIZADO</span>
            <b>{cl.periodo || "—"}</b>
            <small>{`diario, lluvia ${fuenteLluvia(analisis)}`} · {fmt(cl.erosividad?.lluvia_anual_mm != null ? ua.agua(cl.erosividad.lluvia_anual_mm) : null, ua.decAgua)} {`${ua.uAgua} por año`}</small>
          </div>
        </div>

        <div className="inf-mapa-resumen">
          <figure>
            <MapaCampo campo={campo} relleno={relleno} etiquetas ancho={300} alto={205} />
            <figcaption>Primera temporada del plan ({plan.temporadas[0]?.etiqueta})</figcaption>
            <Leyenda plan={plan} catalogo={catalogo} />
          </figure>
          <div className="inf-productor">
            <h2>Lo que contó el productor</h2>
            <ul>
              <li><b>Sistema:</b> {sis.tipo || "no informado"}{sis.ganado ? `, con ganado${sis.cabezas ? ` (${sis.cabezas} cabezas)` : ""}` : ""}; vende forraje: {si(sis.vende_forraje)}; riego: {si(sis.riego)}.</li>
              <li><b>Tenencia:</b> {sis.tenencia || "no informada"}{sis.tenencia === "arrendado" ? `${sis.anios_contrato ? `, ${sis.anios_contrato} años de contrato` : ""}${sis.renta_kg ? `, renta de ${sis.renta_kg} kg de soja por ha` : ""}` : ""}. Seguro de seca: {si(sis.seguro_seca)}; vende a futuro: {si(sis.vende_futuro)}.</li>
              {exp && (exp.que_funciono || exp.que_fallo) && (
                <li><b>Experiencia</b>{exp.anios ? ` (${exp.anios} años en el campo)` : ""}: le anduvo {exp.que_funciono || "—"}; le falló {exp.que_fallo || "—"}.</li>
              )}
              {campo.restricciones?.cultivos_excluidos?.length ? (
                <li><b>No quiere:</b> {campo.restricciones.cultivos_excluidos.map((c) => nombreCultivo(catalogo, c).toLowerCase()).join(", ")}.</li>
              ) : null}
            </ul>
            {pr.length > 0 && (
              <>
                <h4 className="inf-mono">PRIORIDADES (0 A 5)</h4>
                {pr.map(([k, v]) => (
                  <div key={k} className="inf-prio">
                    <span>{PRIORIDAD[k] || k}</span>
                    <i aria-label={`${v} de 5`}>{[0, 1, 2, 3, 4].map((j) => <b key={j} className={j < (v as number) ? "lleno" : ""} />)}</i>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        <h2>Qué se hace en cada sección</h2>
        <table className="inf-resumen">
          <thead><tr><th>Sección</th><th>{u.uSup}</th><th>Hoy</th><th>En el plan</th><th>Erosión hoy → plan</th><th>Tolerancia</th><th /></tr></thead>
          <tbody>
            {analisis.secciones.map((s) => {
              const ep = enPlanDe(s);
              const sg = sugeridaDe(s);
              return (
                <tr key={s.id}>
                  <td><i className="inf-punto" style={{ background: relleno(s.id) }} />{s.nombre}</td>
                  <td className="num">{fmt(u.sup(s.area_ha))}</td>
                  <td>{hoyTexto(s)}</td>
                  <td>
                    <b>{nombreEnPlan(ep)}</b>
                    {sg && sg.id !== ep.id && <small className="inf-sug">sugerida: {nombreEnPlan(sg)}</small>}
                  </td>
                  <td className="num">{fmt(s.actual ? u.eros(s.actual.erosion.a_t_ha) : null, 1)} → <b>{fmt(u.eros(ep.erosion.a_t_ha), 1)}</b></td>
                  <td className="num">{fmt(u.tol(ep.erosion.tolerancia_t))}</td>
                  <td className={`inf-estado ${ep.erosion.cumple ? "ok" : "mal"}`} aria-label={ep.erosion.cumple ? "cumple" : "no cumple"}>{ep.erosion.cumple ? "✓" : "✕"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="inf-aviso">{AVISO_CORTO}</p>
      </div>

      {/* -------- hoja 2: calendario, clima y cómo leer */}
      <div className="inf-hoja">
        <h2>Calendario del plan</h2>
        <p className="inf-nota">Qué ocupa cada sección en cada temporada. Erosión media del campo con el plan: <b>{`${fmt(plan.erosion_media_plan, 1)} t/ha/año`}</b>{` (hoy ${fmt(plan.erosion_media_actual, 1)} t/ha/año).`}</p>
        <Calendario plan={plan} catalogo={catalogo} />
        <Leyenda plan={plan} catalogo={catalogo} />

        <h2>Clima de la zona</h2>
        <div className="inf-clima">
          {t?.lluvia_anual && (
            <div><span className="inf-mono">LLUVIA MEDIA</span><b>{`${fmt(t.lluvia_anual.antes)} → ${fmt(t.lluvia_anual.ahora)} mm`}</b><small>{t.periodo_antes} → {t.periodo_ahora}</small></div>
          )}
          {t?.dias_calor_verano && (
            <div><span className="inf-mono">DÍAS DE CALOR (VERANO)</span><b>{fmt(t.dias_calor_verano.antes, 1)} → {fmt(t.dias_calor_verano.ahora, 1)}</b><small>días de más de 35 °C</small></div>
          )}
          <div><span className="inf-mono">FACTOR R</span><b>{fmt(analisis.factor_r.usado)}</b><small>{analisis.factor_r.fuente.split("(")[0].trim()}</small></div>
        </div>

        <h2>Cómo leer las secciones</h2>
        <p className="inf-nota">
          Cada sección compara lo que se hace hoy con las mejores alternativas. <b>Puntaje:</b> de 0 a 100, ponderado por las prioridades del productor. <b>Erosión:</b> A = R · K · LS · C · P con las relaciones de pérdida de suelo del programa oficial Erosión 6.0 (MGAP - UdelaR); la barra es verde si queda por debajo de la tolerancia del suelo (la línea). <b>Seca:</b> años de cada 10 en que el cultivo llegó a la floración con menos de la mitad del agua que pedía (1991 a hoy).
        </p>
      </div>

      {/* -------- una tarjeta por sección */}
      <div className="inf-hoja inf-tarjetas">
        {analisis.secciones.map((s) => (
          <TarjetaSeccion key={s.id} s={s} enPlan={enPlanDe(s)} sugerida={sugeridaDe(s)} relleno={relleno} />
        ))}
      </div>

      {/* -------- método y fuentes */}
      <div className="inf-hoja">
        <h2>Método y fuentes</h2>
        <ul className="inf-fuentes">
          {analisis.fuentes.map((f) => <li key={f.nombre}><b>{f.nombre}</b> ({f.uso}): <span className="url">{f.url}</span></li>)}
        </ul>
        <p className="inf-nota">No verificado: los cultivos con aproximación propia de factor C (verdeo y cobertura), los coeficientes de cultivo y fechas de siembra (FAO-56, a validar con INIA), los ajustes por lo que marca el productor y por tenencia, y los umbrales de pH, fósforo y potasio.</p>
        <p className="inf-aviso">{AVISO}</p>
      </div>

      <div className="informe-acciones informe-acciones-pie no-imprimir">
        <button className="btn primario" onClick={() => window.print()}>Guardar en PDF</button>
        <button className="btn" onClick={onCerrar}>Cerrar</button>
      </div>
    </div>,
    document.body,
  );
}
