/** Temperatura adentro del potrero con ECOSTRESS (NASA / ISS, 70 m): las pasadas útiles y tres días puntuales.
 * Está calculado a mano solo para el campo de ejemplo (datos/ecostress_demo.json), así que solo se muestra ahí. */

import { useEffect, useState } from "react";
import { api, type DiagnosticoEcostress } from "../api";
import { useApp } from "../store";

const coma = (x: number) => x.toFixed(1).replace(".", ",");
const fecha = (iso: string) => iso.split("-").reverse().join("/");

export function Ecostress() {
  const { esEjemplo: ejemplo, campo } = useApp();
  const esEjemplo = ejemplo && campo.id === "demo-durazno-1000";
  const [datos, setDatos] = useState<DiagnosticoEcostress | null>(null);

  useEffect(() => {
    if (!esEjemplo) return;
    let vivo = true;
    api.ecostress()
      .then((d) => { if (vivo) setDatos(d); })
      .catch(() => { /* sin datos no se muestra */ });
    return () => { vivo = false; };
  }, [esEjemplo]);

  if (!esEjemplo || !datos) return null;

  const diag = datos.diagnostico_campo;
  const fechas = datos.fechas_clave_ejemplo || [];

  return (
    <div className="caja" id="datos-ecostress">
      <h3>Temperatura adentro del potrero (NASA ECOSTRESS, 70 m)</h3>
      <p className="bajada">
        ECOSTRESS mide la temperatura de la superficie desde la Estación Espacial, en cuadraditos de 70 m: alcanza para ver diferencias adentro del potrero. Por ahora está calculado solo para el campo de ejemplo.
      </p>

      {diag && (
        <div style={{ marginBottom: 12, fontSize: 13, lineHeight: 1.5 }}>
          <p style={{ margin: "0 0 6px" }}>
            <strong>{`${diag.pasadas_con_dato_valido} pasadas limpias de ${diag.pasadas_totales_orbita} en los últimos 2 años`}</strong>{" "}
            {`(${coma(diag.porcentaje_util)} % útiles; ${diag.pasadas_con_nube_o_corte} tapadas por nubes o fuera de cuadro).`}
          </p>
          <p className="fuente" style={{ margin: 0 }}>{datos.conclusion}</p>
        </div>
      )}

      {fechas.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 10, marginTop: 10 }}>
          {fechas.map((f) => (
            <div key={f.fecha} style={{ background: "var(--fondo-2)", padding: "10px 12px", borderRadius: 6, fontSize: 12.5 }}>
              <div style={{ fontWeight: 600, color: "var(--texto-1)", marginBottom: 2 }}>{f.evento}</div>
              <div style={{ color: "var(--texto-3)", fontSize: 11.5, marginBottom: 6 }}>
                {`${fecha(f.fecha)}, ${f.hora_local} · media ${coma(f.temperatura_media_c)} °C · de ${coma(f.temperatura_min_c)} a ${coma(f.temperatura_max_c)} °C`}
              </div>
              <div style={{ color: "var(--texto-2)", lineHeight: 1.4 }}>{f.interpretacion}</div>
            </div>
          ))}
        </div>
      )}

      <details className="tecnico" style={{ marginTop: 10 }}>
        <summary>Productos y disponibilidad fuera de EE. UU.</summary>
        <p style={{ margin: "4px 0", fontSize: 12, color: "var(--texto-2)" }}>
          Los productos ALEXI / disALEXI solo cubren EE. UU. continental. Para Uruguay se usa la temperatura de superficie a 70 m (ECO_L2T_LSTE V2 en Earth Engine). El índice de estrés evaporativo global PT-JPL (ECO_L4T_ESI) cubre el país por AppEEARS / LP DAAC.
        </p>
      </details>
    </div>
  );
}
