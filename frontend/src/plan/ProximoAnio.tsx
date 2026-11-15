import { colorCultivo, nombreCorto, useApp } from "../store";
import { IconoCultivo } from "../comun/Cultivo";
import { etiquetaCortaTemporada, nombrePlan } from "./eleccion";

/**
 * Lo primero del Plan. Una fila por lote: qué plan tiene («Plan 1», «Plan actual»…) y qué se siembra en las dos primeras
 * temporadas. Tocar un lote abre sus opciones en «Detalle».
 */
export function ProximoAnio({ alTocarLote }: { alTocarLote: (id: string) => void }) {
  const { plan, analisis, catalogo, seccionSel, temporada, setTemporada } = useApp();
  if (!plan || !analisis) return null;
  const temps = plan.temporadas.slice(0, 2);
  // en el orden de la lista de lotes (la de Comparar), no en el del plan
  const orden = (id: string) => { const i = analisis.secciones.findIndex((s) => s.id === id); return i < 0 ? 999 : i; };
  const filas = [...plan.secciones].sort((a, b) => orden(a.seccion_id) - orden(b.seccion_id));
  return (
    <div className="caja proximo-anio">
      <h3>El plan para el próximo año</h3>
      <p className="bajada">Qué va en cada lote. Tocá uno para ver sus opciones y cambiarlo.</p>
      <table className="proximo-anio-tabla">
        <thead>
          <tr>
            <th>Lote</th>
            {temps.map((t, i) => (
              <th key={i} className={i === temporada ? "sel" : ""} onClick={() => setTemporada(i)} title={t.etiqueta}>{etiquetaCortaTemporada(t)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filas.map((a) => {
            const sec = analisis.secciones.find((s) => s.id === a.seccion_id);
            const nombre = sec ? nombrePlan(sec, a.rotacion_id) : undefined;
            return (
              <tr key={a.seccion_id} className={a.seccion_id === seccionSel ? "sel" : ""} onClick={() => alTocarLote(a.seccion_id)}>
                <th>
                  <span className="proximo-lote">{a.seccion}</span>
                  {nombre && <span className="proximo-plan">{nombre}</span>}
                </th>
                {temps.map((_, i) => {
                  const c = a.cultivos[i];
                  const info = catalogo?.cultivos.find((x) => x.codigo === c);
                  return (
                    <td key={i}>
                      <span className="proximo-cultivo" style={{ borderColor: colorCultivo(catalogo, c) }}>
                        <IconoCultivo icono={info?.icono || "barbecho"} color={info?.color || "#999"} size={16} />
                        {nombreCorto(c)}
                      </span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
