/** Humedad del suelo medida por SMAP (NASA) contra el balance de agua de la app.
 *
 * En Uruguay la serie está al instante (la guardada del ejemplo o la grilla nacional de Earth Engine). En otro país
 * se le pide a AppEEARS, que con SMAP tarda horas: el pedido queda en la caché compartida y una
 * visita posterior ya lo encuentra. El
 * recuadro aparece solo cuando hay datos; mientras tanto, o si falla, no se muestra nada (antes decía «tarda unos
 * minutos; se completa sola», que no era cierto). Se vuelve a preguntar cada 30 s, solo con la pestaña a la vista. */

import { useEffect, useState } from "react";
import { api, type ResultadoSmap } from "../api";
import { useApp } from "../store";
import { GraficoHumedad } from "./Graficos";
import { enPalabras } from "../errores";

const fecha = (iso?: string) => (iso ? iso.split("-").reverse().join("/") : "");

/** La consulta a SMAP, aparte del recuadro: Datos la usa también para saber si el grupo «El agua en tu suelo» tiene
 * algo que mostrar (si no, el grupo y su botón del índice no aparecen). Devuelve null mientras no hay datos. */
export function useSmap(): ResultadoSmap | null {
  const { analisis } = useApp();
  const [res, setRes] = useState<ResultadoSmap | null>(null);
  const secciones = analisis?.secciones || [];
  const lat = secciones.length ? secciones.reduce((a, s) => a + s.punto[0], 0) / secciones.length : null;
  const lon = secciones.length ? secciones.reduce((a, s) => a + s.punto[1], 0) / secciones.length : null;
  const agua = analisis?.clima?.agua_util_mm ?? 120;

  useEffect(() => {
    if (lat == null || lon == null) return;
    let vivo = true;
    let espera: ReturnType<typeof setTimeout> | undefined;
    const preguntar = () => {
      if (document.hidden) { espera = setTimeout(preguntar, 30000); return; }
      api.smap(lat, lon, agua)
        .then((r) => { if (!vivo) return; setRes(r); if (r.estado === "pendiente") espera = setTimeout(preguntar, 30000); })
        .catch((e: Error) => { if (vivo) setRes({ estado: "error", motivo: enPalabras(e) }); });
    };
    preguntar();
    return () => { vivo = false; if (espera) clearTimeout(espera); };
  }, [lat, lon, agua]);

  return lat != null && res?.estado === "listo" && res.ok ? res : null;
}

export function Humedad({ res }: { res: ResultadoSmap | null }) {
  if (!res) return null;
  return (
    <div className="caja">
      <h3>Humedad del suelo vista por SMAP</h3>
      <p className="bajada">El satélite SMAP de la NASA mide la humedad de los primeros centímetros y, combinado con un modelo, la de la zona de raíces (hasta 1 m). Acá se compara con el balance de agua que usa la app para calcular el riesgo de seca.</p>
      {res.ahora && <div className="alerta azul" style={{ marginBottom: 10 }}><b>Ahora ({fecha(res.ahora.hasta)}):</b> {res.ahora.texto}</div>}
      <GraficoHumedad mensual={res.mensual || []} />
      <p style={{ fontSize: 13, margin: "8px 0 0" }}>
        En {res.meses_en_comun} meses en común, SMAP y la app {res.acuerdo} <span className="fuente">(correlación de las anomalías: {String(res.correlacion).replace(".", ",")})</span>
      </p>
      {res.gldas?.frase_secas && (
        <p style={{ fontSize: 13, margin: "6px 0 0" }}>
          <b>Secas históricas (GLDAS 2000-hoy):</b> {res.gldas.frase_secas}
          {res.gldas.correlacion != null && (
            <span className="fuente">{` (correlación r = ${String(res.gldas.correlacion).replace(".", ",")})`}</span>
          )}
        </p>
      )}
      <details className="tecnico">
        <summary>Cómo se compara y sus límites</summary>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--texto-2)" }}>{(res.limites || []).map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="fuente" style={{ marginTop: 6 }}>{res.fuente}{res.gldas_fuente ? ` · ${res.gldas_fuente}` : ""} · {fecha(res.desde)} a {fecha(res.hasta)}</p>
      </details>
    </div>
  );
}
