import { useEffect } from "react";
import { DIMENSIONES } from "../chat/Tarjetas";
import { nombreCultivo, useApp } from "../store";
import type { TipoTarjeta } from "../tipos";

export function RevisarDatos({ onCerrar }: { onCerrar: () => void }) {
  const s = useApp();
  const { campo, catalogo, actualizarCampo, reabrirPaso, iniciarEdicionCampo, rehacerAnalisis } = s;

  useEffect(() => {
    const alTecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCerrar();
    };
    window.addEventListener("keydown", alTecla);
    return () => window.removeEventListener("keydown", alTecla);
  }, [onCerrar]);

  const p = campo.objetivos?.prioridades;

  function irAlMapa(modo?: "ver" | "secciones") {
    iniciarEdicionCampo(modo);
    onCerrar();
  }

  function irAPaso(tipo: TipoTarjeta) {
    reabrirPaso(tipo);
    onCerrar();
  }

  function alRehacerAnalisis() {
    onCerrar();
    void rehacerAnalisis();
  }

  return (
    <div className="modal-fondo" onClick={onCerrar} role="dialog" aria-modal="true" aria-labelledby="modal-revisar-titulo">
      <div className="modal-caja modal-revisar" onClick={(e) => e.stopPropagation()}>
        <div className="modal-revisar-cabecera">
          <div>
            <h2 id="modal-revisar-titulo" style={{ margin: 0, fontSize: 20 }}>Revisar mis datos</h2>
            <p className="bajada" style={{ margin: "4px 0 0" }}>
              Todo lo cargado para armar el análisis y el plan de rotaciones. Podés cambiar cualquier dato y recalcular el informe.
            </p>
          </div>
          <button className="btn chico fantasma" onClick={onCerrar} aria-label="Cerrar ventana" style={{ fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        <div className="modal-revisar-cuerpo">
          <div className="caja">
            <div className="fila" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <h3>El campo</h3>
              <div className="fila" style={{ gap: 6 }}>
                <button className="btn chico" onClick={() => irAlMapa("ver")}>Ver contorno en el mapa</button>
              </div>
            </div>
            <dl className="ficha-dl" style={{ marginTop: 10 }}>
              <dt>Nombre</dt>
              <dd>
                <input
                  className="entrada"
                  value={campo.nombre || ""}
                  placeholder="ej. La Esperanza"
                  onChange={(e) => actualizarCampo({ nombre: e.target.value })}
                  style={{ width: "100%", maxWidth: 300 }}
                />
              </dd>
              <dt>Superficie</dt>
              <dd>{campo.area_ha ? `${campo.area_ha.toLocaleString("es-UY")} ha` : "—"}</dd>
              <dt>Ubicación</dt>
              <dd>
                {campo.ubicacion ? `${campo.ubicacion.lat.toFixed(4)}, ${campo.ubicacion.lon.toFixed(4)}` : "—"}
                {campo.ubicacion?.padron ? ` · padrón ${campo.ubicacion.padron} (${campo.ubicacion.departamento})` : ""}
              </dd>
              <dt>Sistema</dt>
              <dd className="fila-con-accion">
                <span>{campo.sistema ? [campo.sistema.tipo, campo.sistema.ganado ? `ganado${campo.sistema.cabezas ? ` (${campo.sistema.cabezas})` : ""}` : "sin ganado", campo.sistema.tenencia, campo.sistema.riego ? "con riego" : null].filter(Boolean).join(" · ") : "—"}</span>
                <button className="btn chico" onClick={() => irAPaso("datos_sistema")}>Cambiar</button>
              </dd>
              <dt>Experiencia</dt>
              <dd className="fila-con-accion">
                <span>{campo.experiencia ? [campo.experiencia.anios && `${campo.experiencia.anios} años`, campo.experiencia.que_funciono && `anduvo: ${campo.experiencia.que_funciono}`, campo.experiencia.que_fallo && `falló: ${campo.experiencia.que_fallo}`].filter(Boolean).join(" · ") || "—" : "—"}</span>
                <button className="btn chico" onClick={() => irAPaso("problemas")}>Cambiar</button>
              </dd>
              <dt>Corto plazo</dt>
              <dd>{campo.objetivos?.corto_plazo || "—"}</dd>
              <dt>Largo plazo</dt>
              <dd>{campo.objetivos?.largo_plazo || "—"}</dd>
              <dt>No quiere hacer</dt>
              <dd className="fila-con-accion">
                <span>{campo.restricciones?.cultivos_excluidos?.map((c) => nombreCultivo(catalogo, c, true)).join(", ") || "—"}</span>
                <button className="btn chico" onClick={() => irAPaso("prioridades")}>Cambiar</button>
              </dd>
              <dt>Estación</dt>
              <dd className="fila-con-accion">
                <span>{campo.estacion ? `${campo.estacion.archivo} · ${campo.estacion.comparacion?.conclusion || ""}` : "—"}</span>
                <button className="btn chico" onClick={() => irAPaso("subir_estacion")}>Cambiar</button>
              </dd>
              <dt>Márgenes</dt>
              <dd className="fila-con-accion">
                <span>{campo.margenes ? Object.entries(campo.margenes).map(([k, v]) => `${nombreCultivo(catalogo, k, true)} ${v}`).join(" · ") + " USD/ha" : "índice relativo"}</span>
                <button className="btn chico" onClick={() => irAPaso("margenes")}>Cambiar</button>
              </dd>
            </dl>
          </div>

          <div className="grilla-cajas">
            <div className="caja">
              <div className="fila" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <h3>Prioridades</h3>
                <button className="btn chico" onClick={() => irAPaso("prioridades")}>Cambiar</button>
              </div>
              {p ? (
                <div className="barras-puntaje" style={{ marginTop: 10 }}>
                  {DIMENSIONES.map((d) => (
                    <div key={d.id} className="barra-p">
                      <span>{d.t}</span>
                      <div className="pista"><div style={{ width: `${((p[d.id] || 0) / 5) * 100}%`, background: "var(--trigo)" }} /></div>
                      <span>{p[d.id] || 0}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="bajada">Todavía no las cargaste.</p>}
            </div>

            <div className="caja">
              <h3>Prácticas de suelo</h3>
              <p className="bajada">Podés ajustarlas acá directamente o en el paso del sistema productivo.</p>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, marginTop: 14 }}>
                <input
                  type="checkbox"
                  checked={!!campo.curvas_de_nivel}
                  onChange={(e) => actualizarCampo({ curvas_de_nivel: e.target.checked })}
                />
                Siembro en curvas de nivel o tengo terrazas (baja la erosión)
              </label>
            </div>
          </div>

          <div className="caja">
            <div className="fila" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <h3>Secciones</h3>
              <div className="fila" style={{ gap: 6 }}>
                <button className="btn chico" onClick={() => irAlMapa("secciones")}>Editar secciones en el mapa</button>
                <button className="btn chico" onClick={() => irAPaso("historial_seccion")}>Cambiar rotaciones anteriores</button>
                <button className="btn chico" onClick={() => irAPaso("subir_analisis_suelo")}>Cambiar análisis de suelo</button>
              </div>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="tabla-mini" style={{ marginTop: 8 }}>
                <thead><tr><th>Sección</th><th>ha</th><th>Historial</th><th>Problemas</th><th>Análisis de suelo</th></tr></thead>
                <tbody>
                  {campo.secciones.map((x) => (
                    <tr key={x.id}>
                      <td><b>{x.nombre}</b></td>
                      <td>{Math.round(x.area_ha || 0)}</td>
                      <td>{x.historial?.map((h) => `${h.anio}: ${nombreCultivo(catalogo, h.invierno || "barbecho", true)} / ${nombreCultivo(catalogo, h.verano || "barbecho", true)}`).join(" · ") || "—"}</td>
                      <td>{x.problemas?.join(", ") || "—"}</td>
                      <td>{x.analisis_suelo ? [x.analisis_suelo.ph && `pH ${x.analisis_suelo.ph}`, x.analisis_suelo.materia_organica && `MO ${x.analisis_suelo.materia_organica} %`].filter(Boolean).join(" · ") : campo.analisis_suelo_general ? "general" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="modal-revisar-pie">
          <button className="btn" onClick={onCerrar}>Cerrar</button>
          <button className="btn primario" onClick={alRehacerAnalisis}>Rehacer el análisis y el informe</button>
        </div>
      </div>
    </div>
  );
}
