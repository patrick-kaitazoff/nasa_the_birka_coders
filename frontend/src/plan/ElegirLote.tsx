import { useState } from "react";
import { useApp } from "../store";
import { DiezAnios } from "./DiezAnios";
import { elegidaDe, planesDe, sugeridaDe } from "./eleccion";

function fmt(n: number, d = 0) {
  return n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

/** Al costado del mapa del Plan: la rotación de hoy del lote tocado y sus alternativas, cada una con su erosión contra
 * lo que aguanta el suelo, lo que la herramienta no sabe y lo que hay que revisar con el agrónomo. La sugerida lleva
 * su etiqueta y su porqué, pero la elige el productor. */
export function ElegirLote({ seccionId }: { seccionId: string }) {
  const { analisis, plan, elegirRotacion, setPestania, setSeccionSel } = useApp();
  const [ocupado, setOcupado] = useState<string | null>(null);
  const sec = analisis?.secciones.find((s) => s.id === seccionId);
  if (!sec || !plan) return null;
  const elegida = elegidaDe(plan, sec);
  const sugerida = sugeridaDe(plan, sec);
  // en el mismo orden y con el mismo nombre que en Comparar: «Plan actual», «Plan 1»…
  const planes = planesDe(sec);
  const ops = planes.map((x) => x.ev);
  const planDe = (id: string) => planes.find((x) => x.ev.id === id)?.plan;
  const evSug = ops.find((o) => o.id === sugerida);
  const pend = sec.suelo?.pendiente_pct;
  const tol = sec.suelo?.tolerancia_t ?? sec.actual?.erosion.tolerancia_t;
  const ningunaCumple = sec.alternativas.length > 0 && sec.alternativas.every((a) => !a.erosion.cumple);

  async function elegir(id: string) {
    if (id === elegida || ocupado) return;
    setOcupado(id);
    try { await elegirRotacion(sec!.id, id); } finally { setOcupado(null); }
  }

  // cada dato en su propio texto, así el traductor de la pantalla los reconoce por separado
  const detalle = [`${fmt(sec.area_ha)} ha`, pend != null ? `pendiente ${fmt(pend, 1)} %` : null, tol != null ? `el suelo aguanta ${fmt(tol)} t/ha/año` : null]
    .filter(Boolean) as string[];

  return (
    <div className="caja elegir-lote">
      <div className="elegir-lote-cab">
        <h3>{sec.nombre}</h3>
        <span className="bajada">{detalle.map((d, i) => <span key={d}>{i > 0 && " · "}<span>{d}</span></span>)}</span>
      </div>
      {evSug && evSug.id !== "actual" && (
        <p className="elegir-lote-sugerida">
          {`Sugerido: ${planDe(evSug.id)}, ${evSug.nombre.replace(/^./, (c) => c.toLowerCase())}. ${evSug.explicacion?.por_que?.[0] || ""}`}
        </p>
      )}
      {evSug && evSug.id === "actual" && <p className="elegir-lote-sugerida">Sugerido: el plan actual, seguir como hasta ahora en este lote.</p>}
      {ningunaCumple && sec.nota_tolerancia && <div className="alerta ambar">{`${sec.nota_tolerancia}.`}</div>}

      <div className="elegir-lote-opciones" role="radiogroup" aria-label={`Opciones para ${sec.nombre}`}>
        {ops.map((o) => {
          const on = o.id === elegida;
          const esHoy = o.id === "actual";
          return (
            <div key={o.id} className={`op-lote ${on ? "on" : ""}`}>
              <button type="button" role="radio" aria-checked={on} className="op-lote-elegir" disabled={!!ocupado} onClick={() => void elegir(o.id)}>
                <span className={`op-lote-marca ${on ? "on" : ""}`} aria-hidden />
                <span className="op-lote-nombre"><b className="op-lote-plan">{planDe(o.id)}</b>{esHoy ? "Seguir como hasta ahora" : o.nombre}</span>
                <span className="op-lote-etqs">
                  {o.id === sugerida && <span className="etq rec">sugerido</span>}
                  {ocupado === o.id && <span className="etq">rearmando…</span>}
                </span>
              </button>
              {esHoy && o.descripcion && <div className="op-lote-desc">{o.descripcion}</div>}
              {/* Solo lo que hace falta para elegir; el detalle (barra de erosión, las cinco explicaciones,
                  riesgos) está en Comparar, a un toque con «Ver la comparación completa» */}
              <div className="op-lote-clave">
                <div className="op-lote-seca">
                  <span className="op-lote-seca-val">Agua en floración, de cada 10 años</span>
                  <DiezAnios p={o.riesgo.seca} />
                </div>
                <div className="op-lote-datos">
                  {o.erosion.exigible === false
                    ? <span>Plan de Uso: no se exige en campo natural</span>
                    : <span className={o.erosion.cumple ? "bien" : "mal"}>{o.erosion.cumple ? "Cumple con el Plan de Uso" : "No cumple con el Plan de Uso"}</span>}
                  {/* Sin «Ingreso relativo»; el margen, si lo cargó */}
                  {o.ingreso.usa_margenes && o.ingreso.usd_ha_anio != null && <span>{`Margen: ${fmt(o.ingreso.usd_ha_anio)} USD/ha`}</span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <p className="elegir-lote-pie">El sugerido es el que mejor encaja con tus prioridades según estos datos. La decisión es tuya.</p>
      <button type="button" className="btn chico" onClick={() => { setSeccionSel(sec.id); setPestania("comparar"); }}>Ver la comparación completa de este lote</button>
    </div>
  );
}
