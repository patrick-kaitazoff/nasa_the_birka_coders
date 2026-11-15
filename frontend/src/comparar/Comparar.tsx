import { useEffect, useState } from "react";
import { api } from "../api";
import { nombreCorto, useApp } from "../store";
import { BarraErosion, escalaErosion, VentanaPeligro } from "../analisis/Graficos";
import { fuenteLluvia } from "../comun/fuenteLluvia";
import { IconoCultivo } from "../comun/Cultivo";
import { planesDe, sugeridaDe } from "../plan/eleccion";
import type { Analisis, Evaluacion, RangoErosion } from "../tipos";

const DIM: Array<[string, string]> = [
  ["suelo", "Suelo"], ["agua", "Agua"], ["clima", "Helada y calor"], ["ingreso", "Ingreso"],
  ["forraje", "Forraje"], ["simplicidad", "Simplicidad"], ["diversificacion", "Diversificación"],
];
const CINCO: Array<[keyof NonNullable<Evaluacion["explicacion"]>, string]> = [
  ["por_que", "Por qué"], ["evidencia", "Evidencia"], ["beneficios", "Beneficios"], ["huecos", "Lo que falta saber"], ["riesgos", "Riesgos"],
];

function Secuencia({ anios }: { anios: [string, string][] }) {
  const { catalogo } = useApp();
  const crudos: string[] = [];
  for (const [inv, ver] of anios) {
    if (inv === ver) crudos.push(inv);
    else crudos.push(inv, ver);
  }
  const pasos: string[] = [];
  const veces: number[] = [];
  for (const c of crudos) {
    if (pasos.length && pasos[pasos.length - 1] === c) veces[veces.length - 1]++;
    else { pasos.push(c); veces.push(1); }
  }
  return (
    <div className="secuencia">
      {pasos.map((c, i) => {
        const info = catalogo?.cultivos.find((x) => x.codigo === c);
        return (
          <span key={i} style={{ display: "contents" }}>
            {i > 0 && <span style={{ color: "var(--texto-3)" }}>→</span>}
            <span className="paso-cultivo"><IconoCultivo icono={info?.icono || "barbecho"} color={info?.color || "#999"} size={16} />{nombreCorto(c)}{veces[i] > 1 ? ` ×${veces[i]} años` : ""}</span>
          </span>
        );
      })}
      <span style={{ color: "var(--texto-3)" }}>↺</span>
    </div>
  );
}

function Aportes({ anios }: { anios: [string, string][] }) {
  const { catalogo } = useApp();
  if (!catalogo?.aportes) return null;
  const codigos = [...new Set(anios.flat())];
  const filas = Object.entries(catalogo.aportes)
    .map(([k, a]) => ({ k, a, cultivos: codigos.filter((c) => catalogo.cultivos.find((x) => x.codigo === c)?.aportes?.includes(k)) }))
    .filter((f) => f.cultivos.length);
  if (!filas.length) {
    return <p style={{ fontSize: 12.5, color: "var(--texto-3)", margin: 0 }}>Ningún cultivo de esta rotación fija nitrógeno, cubre ni recupera el suelo, tiene raíz profunda ni aguanta la seca.</p>;
  }
  return (
    <div className="cinco">
      <div style={{ fontWeight: 650, fontSize: 13, padding: "6px 0 2px" }}>Qué le aporta al suelo</div>
      {filas.map(({ k, a, cultivos }) => (
        <details key={k}>
          <summary>{a.nombre}<span style={{ fontWeight: 400, color: "var(--texto-3)", marginLeft: "auto", marginRight: 8 }}>{cultivos.map((c) => nombreCorto(c)).join(", ")}</span></summary>
          <ul><li>{a.explicacion}</li></ul>
        </details>
      ))}
    </div>
  );
}

/** Rango de la erosión de cada opción: viene en el análisis; si es un análisis guardado antes (el campo de
 * ejemplo), se le pide al backend con los mismos factores. */
function useRangos(opciones: Evaluacion[], rAlt: Array<number | null>) {
  const [extra, setExtra] = useState<Record<string, RangoErosion | null>>({});
  const [supuestos, setSupuestos] = useState<string[]>([]);
  const faltan = opciones.filter((o) => o.erosion.rango === undefined && !(o.id in extra));
  const clave = faltan.map((o) => o.id).join(",");
  useEffect(() => {
    if (!faltan.length && supuestos.length) return;
    let vivo = true;
    api.rangoErosion(faltan.map((o) => o.erosion), rAlt).then((r) => {
      if (!vivo) return;
      setSupuestos(r.supuestos);
      if (faltan.length) setExtra((e) => ({ ...e, ...Object.fromEntries(faltan.map((o, i) => [o.id, r.rangos[i]])) }));
    }).catch(() => { /* sin rango, la barra queda como antes */ });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave]);
  return { rango: (o: Evaluacion) => (o.erosion.rango !== undefined ? o.erosion.rango : extra[o.id]), supuestos };
}

function fmtN(n: number, d = 0) {
  return n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

/** Los cuatro datos que deciden, arriba de cada tarjeta: seca en floración, cuánto pierde un año seco, si pasa el Plan de Uso y el ingreso. Así las tarjetas
 * se comparan una al lado de la otra sin bajar. */
function DatosClave({ ev }: { ev: Evaluacion }) {
  const perdida = ev.riesgo.perdida_anio_seco;
  // Cada dato es su número; las aclaraciones
  // pasan al cartelito del mouse. El único color es el del Plan de Uso, que es lo que se aprueba o no.
  return (
    <div className="opcion-clave">
      <div className="opcion-dato" title="Años en que los cultivos llegan a la floración con menos de la mitad del agua que necesitan">
        <div className="k">Seca en floración</div>
        <div className="v">{`${fmtN(ev.riesgo.seca * 10, 1)} de cada 10 años`}</div>
      </div>
      <div className="opcion-dato" title={perdida != null ? "Lo que se pierde de rinde en un año seco, contra un año con agua suficiente" : "Sin cultivos de cosecha: no hay grano que perder"}>
        <div className="k">Un año seco pierde</div>
        <div className="v">{perdida != null ? `${fmtN(perdida * 100)} % del rinde` : "Sin grano"}</div>
      </div>
      <div className={`opcion-dato ${ev.erosion.exigible === false ? "" : ev.erosion.cumple ? "bien" : "mal"}`}
        title={`Erosión ${fmtN(ev.erosion.a_t_ha, 1)} t/ha/año; el suelo aguanta ${fmtN(ev.erosion.tolerancia_t)}`}>
        <div className="k">Plan de Uso</div>
        <div className="v">{ev.erosion.exigible === false ? "No se exige" : ev.erosion.cumple ? "Cumple" : "No cumple"}</div>
        <div className="s">{`erosión ${fmtN(ev.erosion.a_t_ha, 1)} de ${fmtN(ev.erosion.tolerancia_t)} t/ha`}</div>
      </div>
      <div className="opcion-dato" title={ev.ingreso.usa_margenes ? "Margen por año, en promedio" : "Índice para comparar entre opciones; no es dinero"}>
        <div className="k">{ev.ingreso.usa_margenes ? "Margen" : "Ingreso relativo"}</div>
        <div className="v">{ev.ingreso.usa_margenes && ev.ingreso.usd_ha_anio != null ? `${fmtN(ev.ingreso.usd_ha_anio)} USD/ha` : fmtN(ev.ingreso.indice_relativo ?? 0, 2)}</div>
      </div>
    </div>
  );
}

/** La recomendada es la que sale primera más seguido con pesos parecidos a los del productor (ver
 * 22-ponderacion.md). Casi siempre es también la de más puntaje; cuando no, se dice por qué. */
function porQueRecomendada(s: Analisis["secciones"][number], opciones: Evaluacion[]): string | null {
  const ac = s.aceptabilidad;
  const rec = opciones.find((o) => o.id === s.recomendada_id);
  if (!ac || !rec || ac[rec.id] == null) return null;
  const otra = opciones
    .filter((o) => o.id !== rec.id && ac[o.id] != null && o.puntaje_total > rec.puntaje_total)
    .sort((a, b) => b.puntaje_total - a.puntaje_total)[0];
  if (!otra) return null;
  const nombre = otra.es_actual ? "lo que hacés hoy" : otra.nombre.replace(/^./, (c) => c.toLowerCase());
  const dif = Math.round(otra.puntaje_total - rec.puntaje_total) || 1;
  return `Puntúa ${dif} menos que ${nombre}, pero con pesos parecidos a los tuyos, en el mismo orden de prioridades, sale primera más seguido: ${ac[rec.id]} de cada 100 contra ${ac[otra.id]}.`;
}

function Opcion({
  ev,
  plan,
  recomendada,
  elegida,
  onElegir,
  rango,
  ningunaCumple,
  escala,
  porQue,
}: {
  ev: Evaluacion;
  /** «Plan actual», «Plan 1»… */
  plan: string;
  recomendada: boolean;
  elegida: boolean;
  onElegir: () => void;
  rango?: RangoErosion | null;
  ningunaCumple?: boolean;
  escala?: number;
  porQue?: string | null;
}) {
  return (
    <div className={`opcion ${recomendada ? "recomendada" : ""} ${elegida ? "elegida" : ""}`}>
      {/* Arriba, el nombre corto del
          plan, el puntaje, qué es y su secuencia de cultivos. Una sola etiqueta (la sugerida o la que está en el plan);
          si cumple el Plan de Uso ya lo dice su dato, y el porqué, la evidencia y los riesgos van plegados */}
      <div className="opcion-cab">
        <div className="opcion-plan-fila">
          <span className="opcion-plan">{plan}</span>
          {recomendada && <span className="etq rec">{ningunaCumple ? "Menor erosión" : "Sugerido"}</span>}
          {elegida && !recomendada && <span className="etq">En el plan</span>}
          <span className="puntaje-total" title="Puntaje según tus prioridades, de 0 a 100"><b>{Math.round(ev.puntaje_total)}</b><span>/ 100</span></span>
        </div>
        <h4>{ev.es_actual ? "Lo que hacés hoy" : ev.nombre}</h4>
        <Secuencia anios={ev.anios} />
        {recomendada && porQue && <p className="por-que-rec">{porQue}</p>}
      </div>
      <div className="opcion-cuerpo">
        <DatosClave ev={ev} />
        {ev.explicacion && (
          <details className="opcion-detalle">
            <summary>Por qué, evidencia y riesgos</summary>
            <div className="cinco">
              {CINCO.map(([k, t]) => (
                <details key={k} open={k === "por_que"}>
                  <summary>{t} <span style={{ fontWeight: 400, color: "var(--texto-3)", marginLeft: "auto", marginRight: 8 }}>{ev.explicacion![k].length}</span></summary>
                  <ul>{ev.explicacion![k].map((x, i) => <li key={i}>{x}</li>)}</ul>
                </details>
              ))}
            </div>
          </details>
        )}
        <details className="opcion-detalle">
          <summary>Erosión, aportes al suelo y puntaje por tema</summary>
          <BarraErosion a={ev.erosion.a_t_ha} t={ev.erosion.tolerancia_t} rango={rango} escala={escala} />
          <Aportes anios={ev.anios} />
          <div className="barras-puntaje">
            {DIM.map(([k, t]) => (
              <div key={k} className="barra-p">
                <span>{t}</span>
                <div className="pista"><div style={{ width: `${ev.puntajes[k]}%`, background: "var(--verde-500)" }} /></div>
                <span>{ev.puntajes[k]}</span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 12.5, color: "var(--texto-2)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 10px" }}>
            <span>Suelo descubierto: <b>{ev.meses_descubierto.length} meses</b></span>
            <span>Carbono del suelo: <b>{ev.carbono.tendencia}</b></span>
          </div>
        </details>
        {/* La elegida ya no es un botón pálido que parece apagado, sino una pastilla de color
            de la paleta; las demás dicen «Elegir para el plan» */}
        {elegida ? (
          <div className="opcion-en-plan" role="status">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M20 6 9 17l-5-5" /></svg>
            <span>En el plan</span>
          </div>
        ) : (
          <button className="btn" onClick={onElegir}>Elegir para el plan</button>
        )}
      </div>
    </div>
  );
}

/** Los temas del puntaje, en minúscula, para «Se destaca en / Flaquea en». */
const TEMA: Record<string, string> = {
  suelo: "suelo", agua: "agua", clima: "helada y calor", ingreso: "ingreso", forraje: "forraje",
  simplicidad: "simplicidad", diversificacion: "diversificación",
};

/** Todas las rotaciones que se probaron en el lote, plegadas al final de Comparar. Antes mostraba puntaje, erosión y una tolerancia que se
 * repetía en cada fila, y parecía que la erosión era lo único que contaba. Ahora tiene los mismos datos que las
 * tarjetas (seca y Plan de Uso) y en qué se destaca y flaquea cada una, que explica el orden sin un puntaje con
 * decimales que aparenta más precisión de la que tiene. */
function TodasLasRotaciones({ s, enPlan, sugerida }: { s: Analisis["secciones"][number]; enPlan?: string; sugerida?: string | null }) {
  const { campo } = useApp();
  const sis = campo.sistema;
  const conGanado = !!sis?.ganado || sis?.tipo === "ganadero" || sis?.tipo === "mixto";
  const temas = Object.keys(TEMA).filter((k) => k !== "forraje" || conGanado);
  const tol = s.todas[0]?.erosion.tolerancia_t;
  // en qué se destaca y flaquea cada una FRENTE A LAS OTRAS del lote: con el puntaje a secas, «helada y calor» salía
  // arriba en casi todas (en Uruguay casi ninguna sufre heladas) y no distinguía nada
  const media: Record<string, number> = Object.fromEntries(temas.map((k) => {
    const vs = s.todas.map((r) => r.puntajes[k]).filter((v) => v != null);
    return [k, vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : 0];
  }));
  const extremos = (p: Record<string, number>) => {
    const ks = temas.filter((k) => p[k] != null);
    if (!ks.length) return null;
    const d = (k: string) => p[k] - media[k];
    const alto = ks.reduce((a, b) => (d(b) > d(a) ? b : a));
    const bajo = ks.reduce((a, b) => (d(b) < d(a) ? b : a));
    return { alto: d(alto) >= 5 ? alto : null, bajo: d(bajo) <= -5 ? bajo : null };
  };
  return (
    <details className="caja todas-rotaciones">
      <summary>{`Ver las ${s.todas.length} rotaciones que se probaron en ${s.nombre}`}</summary>
      <p className="bajada">
        {tol != null
          ? `Ordenadas de la que mejor encaja con tus prioridades a la que menos. Este suelo aguanta ${fmtN(tol)} t/ha/año de erosión: las que se pasan bajan en el orden.`
          : "Ordenadas de la que mejor encaja con tus prioridades a la que menos."}
      </p>
      <div className="todas-rotaciones-marco">
        <table className="tabla-mini todas-rotaciones-tabla">
          <thead>
            <tr><th>Rotación</th><th>Seca en floración</th><th>Plan de Uso</th><th>Se destaca en</th><th>Flaquea en</th></tr>
          </thead>
          <tbody>
            {s.todas.map((r) => {
              const ex = extremos(r.puntajes);
              const seca = r.riesgo?.seca;
              return (
                <tr key={r.id} className={r.id === enPlan ? "en-plan" : ""}>
                  <td className="nom"><div>
                    <span>{r.nombre}</span>
                    {r.id === s.actual?.id && <span className="etq actual">hoy</span>}
                    {r.id === sugerida && <span className="etq rec">sugerida</span>}
                    {r.id === enPlan && r.id !== sugerida && <span className="etq">en el plan</span>}
                  </div></td>
                  <td>{seca != null ? `${fmtN(seca * 10, 1)} de cada 10` : "—"}</td>
                  <td>
                    <span className={`etq ${r.erosion.exigible === false ? "neutra" : r.erosion.cumple ? "bien" : "mal"}`}>
                      {r.erosion.exigible === false ? "No se exige" : r.erosion.cumple ? "Cumple" : "No cumple"}
                    </span>
                    <small>{`${fmtN(r.erosion.a_t_ha, 1)} t/ha/año`}</small>
                  </td>
                  <td>{ex?.alto ? TEMA[ex.alto] : "—"}</td>
                  <td>{ex?.bajo ? TEMA[ex.bajo] : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function Comparar() {
  const { analisis, plan, seccionSel, seccionAuto, setSeccionSel, setSeccionAuto, elegirRotacion } = useApp();
  // arranca en el primer lote de la izquierda, salvo que la persona haya tocado uno (en el plano, la tabla o «Ver la
  // comparación completa de este lote»); antes heredaba el más grande que marca solo el Plan
  useEffect(() => {
    if (!analisis) return;
    const primero = analisis.secciones[0]?.id || null;
    if (!seccionSel || !analisis.secciones.find((s) => s.id === seccionSel) || (seccionAuto && seccionSel !== primero)) setSeccionAuto(primero);
  }, [analisis, seccionSel, seccionAuto, setSeccionAuto]);
  const sVista = analisis ? analisis.secciones.find((x) => x.id === seccionSel) || analisis.secciones[0] : undefined;
  const opcionesVista = sVista ? ([sVista.actual, ...sVista.alternativas].filter(Boolean) as Evaluacion[]) : [];
  const { rango, supuestos } = useRangos(opcionesVista,
    // con un R medido (terrenos de ejemplo de fuera de Uruguay) el rango no se abre hasta el de la fórmula
    analisis?.factor_r?.medido ? [] : [analisis?.factor_r?.mgap?.r ?? null, analisis?.factor_r?.nasa ?? null]);

  if (!analisis) {
    return <div className="vacio"><div className="caja"><h3>Sin análisis todavía</h3><p>Cuando se analice el campo, acá vas a comparar la rotación actual con las alternativas, sección por sección.</p></div></div>;
  }
  const s = analisis.secciones.find((x) => x.id === seccionSel) || analisis.secciones[0];
  const planes = planesDe(s);
  const opciones = planes.map((x) => x.ev);
  const planDe = (o: Evaluacion) => planes.find((x) => x.ev.id === o.id)?.plan || o.nombre;
  const ningunaCumple = s.alternativas.length > 0 && s.alternativas.every((a) => !a.erosion.cumple);
  const enPlan = plan?.secciones.find((a) => a.seccion_id === s.id)?.rotacion_id;
  // «Sugerido» es la misma opción que sugiere el Plan (la del reparto agrícola-ganadero del campo), no la
  // de más puntaje del lote suelto: en un campo mixto de Soriano el Plan sugería el Plan 3 y acá la etiqueta estaba
  // en el Plan 1
  const sugerida = sugeridaDe(plan, s) ?? s.recomendada_id;
  const mejorSola = sugerida !== s.recomendada_id ? opciones.find((o) => o.id === s.recomendada_id) : undefined;
  const porQueSugerida = mejorSola
    ? `Es la sugerida para llegar a la parte agrícola que pediste en todo el campo. Mirando solo este lote, la de más puntaje es ${planDe(mejorSola)}.`
    : porQueRecomendada(s, opciones);
  const reparto: number[] = analisis.clima.erosividad.reparto_mensual;
  const tormentas = analisis.clima?.tormentas;
  const partesTormentas = tormentas && tormentas.por_mes?.length === 12
    ? opciones.map((o) => {
        const cuantas = tormentas.por_mes.reduce((acc: number, p: number, m: number) => acc + p * (1 - (o.cobertura_mensual[m] ?? 0)), 0);
        return {
          id: o.id,
          nombre: planDe(o),
          cuantas: fmtN(cuantas, 1),
          esActual: !!o.es_actual,
          esRec: o.id === sugerida,
        };
      })
    : [];
  // una sola escala para las barras de erosión de todas las opciones del lote, así se comparan a simple vista
  const escala = Math.max(...opciones.map((o) => escalaErosion(o.erosion.a_t_ha, o.erosion.tolerancia_t, rango(o))));


  return (
    <div className="panel panel-comparar">
      <div className="panel-titulo">
        <div>
          <h2>Comparar rotaciones</h2>
          <p>Lo que hacés hoy contra las mejores alternativas de cada lote. El puntaje pondera tus prioridades; la decisión es tuya.</p>
        </div>
        {/* Fuera la pastilla «Plan desde el verano… hasta el invierno…» */}
      </div>

      <div className="selector-seccion">
        {analisis.secciones.map((x) => (
          <button key={x.id} className={`chip ${x.id === s.id ? "on" : ""}`} onClick={() => setSeccionSel(x.id)}>
            {x.nombre} · {`${Math.round(x.area_ha)} ha`}
          </button>
        ))}
      </div>


      <div className="opciones-cab">
        <div>
          <h3>{`Opciones para ${s.nombre}`}</h3>
        </div>
      </div>

      {ningunaCumple && s.nota_tolerancia && (
        <div className="aviso-alerta-tolerancia">
          <div className="aviso-alerta-icono">⚠</div>
          <div className="aviso-alerta-cuerpo">
            <strong>Este suelo aguanta poca erosión</strong>
            <p>{s.nota_tolerancia}.</p>
          </div>
        </div>
      )}

      <div className="opciones">
        {opciones.map((o) => (
          <Opcion
            key={o.id}
            ev={o}
            plan={planDe(o)}
            recomendada={o.id === sugerida}
            elegida={o.id === enPlan}
            onElegir={() => void elegirRotacion(s.id, o.id)}
            rango={rango(o)}
            ningunaCumple={ningunaCumple}
            escala={escala}
            porQue={porQueSugerida}
          />
        ))}
        {/* Si ya hay una tarjeta que supera la tolerancia (se suman para comparar al menos tres
            estrategias), el cartel la repetiría */}
        {s.nota_tolerancia && !ningunaCumple && s.alternativas.every((a) => a.erosion.cumple) && (
          <div className="opcion opcion-nota">
            <div className="opcion-cab">
              {/* Sin la etiqueta roja «Supera tolerancia»: esto explica por qué no hay más opciones, no es
                  una opción que se pueda elegir */}
              <h4>{s.nota_tolerancia.startsWith("Con solo cultivos") ? "Solo cultivos" : s.nota_tolerancia.startsWith("Ninguna") ? "Otras rotaciones" : "Con pasturas o ganado"}</h4>
              <div className="opcion-periodo">Por qué no hay más opciones</div>
            </div>
            <div className="opcion-cuerpo">
              <p className="nota-tolerancia-texto">{s.nota_tolerancia}.</p>
              <p className="nota-tolerancia-bajada">
                Un Plan de Uso que supera la tolerancia del suelo no se aprueba. En la tabla de abajo podés ver todas las rotaciones evaluadas.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Va después de las tarjetas (antes ocupaba la primera pantalla y la comparación quedaba abajo) */}
      <div className="caja">
        <h3>¿Cuándo queda el suelo expuesto a la lluvia que erosiona?</h3>
        <p className="bajada">Abajo, cuánto suelo cubre cada opción mes a mes. Los recuadros rojos son los meses de peligro: suelo descubierto con lluvia fuerte.</p>
        <VentanaPeligro reparto={reparto} filas={opciones.map((o) => ({ t: planDe(o), cobertura: o.cobertura_mensual, destacada: o.id === sugerida }))} fuente={fuenteLluvia(analisis)} />
        {tormentas && partesTormentas.length > 0 && (
          <p className="bajada" style={{ marginTop: 12 }}>
            <span>{`De las ${fmtN(tormentas.por_anio, 1)} lluvias de 50 mm o más que caen por año (${tormentas.fuente} ${tormentas.periodo})`}</span>
            {partesTormentas.map((p, idx) => {
              const texto = idx === 0
                ? `, con el ${p.nombre} ${p.cuantas} caen con el suelo descubierto`
                : `; con el ${p.nombre}, ${p.cuantas}`;
              return p.esRec ? (
                <strong key={p.id} style={{ color: "var(--color-primario, #1f6f54)" }}>
                  {texto}
                </strong>
              ) : (
                <span key={p.id}>{texto}</span>
              );
            })}
            .
          </p>
        )}
      </div>
      {supuestos.length > 0 && (
        <div className="caja">
          <h3>Qué tan seguro es cada número</h3>
          <p className="bajada">La erosión de cada opción se calcula 4.000 veces moviendo, dentro de rangos razonables, los datos que tienen más duda. La raya fina sobre la barra marca dónde cae 8 de cada 10 veces, y al lado dice en qué porcentaje de los casos supera la tolerancia del suelo. Los «años de cada 10» de la pestaña Datos llevan su rango por la misma razón: salen de unos 35 años, no de cientos.</p>
          <details className="tecnico">
            <summary>Supuestos de la simulación</summary>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--texto-2)" }}>{supuestos.map((x) => <li key={x}>{x}</li>)}</ul>
          </details>
        </div>
      )}

      <TodasLasRotaciones s={s} enPlan={enPlan} sugerida={sugerida} />
    </div>
  );
}
