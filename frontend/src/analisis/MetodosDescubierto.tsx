/** Dos métodos para detectar el suelo descubierto con el NDVI de la sección: corte fijo contra corte
 * automático (Otsu). El cálculo está en el backend (analisis/descubierto.py); para análisis guardados antes
 * de que existiera (el campo de ejemplo) se pide a /api/descubierto con la serie que ya está. */
import { useEffect, useState } from "react";
import { api, type ComparacionDescubierto } from "../api";

const MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const coma = (n: number, d = 2) => n.toFixed(d).replace(".", ",");

export function useMetodosDescubierto(ndvi: { mensual?: Array<{ anio: number; mes: number; ndvi: number }>; metodos?: ComparacionDescubierto }) {
  const [res, setRes] = useState<ComparacionDescubierto | null>(ndvi.metodos || null);
  const clave = ndvi.mensual?.length ? `${ndvi.mensual[0].anio}-${ndvi.mensual.length}-${ndvi.mensual[ndvi.mensual.length - 1].ndvi}` : "";
  useEffect(() => {
    if (ndvi.metodos) { setRes(ndvi.metodos); return; }
    setRes(null);
    if (!ndvi.mensual?.length) return;
    let vivo = true;
    api.descubierto(ndvi.mensual).then((r) => { if (vivo) setRes(r); }).catch(() => { /* sin la comparación sigue todo igual */ });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave, ndvi.metodos]);
  return res;
}

export function MetodosDescubierto({ res }: { res: ComparacionDescubierto | null }) {
  if (!res) return null;
  if (!res.ok) return <p className="fuente" style={{ marginTop: 8 }}>{res.motivo}</p>;
  const [fijo, otsu] = res.metodos;
  return (
    // Plegado, como el «Detalle técnico» del suelo; es para el agrónomo y alargaba cada sección
    <details className="tecnico metodos-descubierto">
      <summary>Dos métodos para detectar el suelo descubierto</summary>
      <p className="bajada" style={{ marginTop: 0 }}>Con el mismo NDVI de {res.anios} años: un corte fijo para todo el país y un corte que el método calcula solo para esta sección.</p>
      <table className="tabla-mini">
        <thead><tr><th>Método</th><th>Corte de NDVI</th><th>Meses descubierto por año</th></tr></thead>
        <tbody>
          <tr><td>{fijo.nombre}</td><td>{coma(fijo.corte!)}</td><td>{coma(fijo.meses_por_anio!, 1)}</td></tr>
          <tr><td>{otsu.nombre}</td><td>{otsu.aplica ? coma(otsu.corte!) : "no aplica"}</td><td>{otsu.aplica ? coma(otsu.meses_por_anio!, 1) : "no aplica"}</td></tr>
        </tbody>
      </table>
      {res.coincidencia_pct != null && (
        <p style={{ fontSize: 13, margin: "8px 0 0" }}>
          {/* frases enteras, no en pedazos: el traductor no reconocía « de los » ni « meses» sueltos */}
          <b>{`Coinciden en el ${res.coincidencia_pct} % de los ${res.meses} meses`}</b>
          {res.kappa != null && <span className="fuente">{` (kappa de Cohen ${coma(res.kappa)}: coincidencia descontando el azar)`}</span>}.
        </p>
      )}
      <div className="alerta azul" style={{ marginTop: 8 }}>{res.lectura}</div>
      {otsu.aplica && res.distintos.length > 0 && (
        <p className="fuente" style={{ marginTop: 6 }}>
          {`Meses en que no coinciden (los últimos): ${res.distintos.map((d) => `${MES[d.mes - 1]} ${d.anio} (${coma(d.ndvi)})`).join(", ")}.`}
        </p>
      )}
      <details className="tecnico">
        <summary>Cómo funciona cada uno</summary>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--texto-2)" }}>
          <li>Corte fijo: NDVI menor a 0,30 es suelo desnudo o rastrojo seco. Simple y comparable entre campos, pero el suelo desnudo no da el mismo NDVI en todas partes (color del suelo, humedad, rastrojo).</li>
          <li>Corte automático (método de Otsu, 1979): busca el número que mejor separa la serie de esta sección en un grupo bajo y uno alto. No se entrena con nada y se adapta al suelo, pero solo vale si la sección pasó por los dos estados y el grupo bajo parece suelo (NDVI promedio de 0,40 o menos); si no, separaría la época verde de la seca del pasto.</li>
          <li>Donde no coinciden es la zona gris: conviene mirarla en el campo o con la imagen de 30 m.</li>
        </ul>
      </details>
    </details>
  );
}
