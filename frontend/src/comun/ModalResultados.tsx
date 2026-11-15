import { useEffect } from "react";
import { useApp } from "../store";

/** Modal informativo al terminar el análisis: resumen de resultados y guía rápida de qué mirar. */
export function ModalResultados() {
  const { campo, mostrarGuiaResultados, setMostrarGuiaResultados, setPestania, setVistaMovil } = useApp();

  // Escape la cierra
  useEffect(() => {
    if (!mostrarGuiaResultados) return;
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      setMostrarGuiaResultados(false);
    };
    window.addEventListener("keydown", tecla, true);
    return () => window.removeEventListener("keydown", tecla, true);
  }, [mostrarGuiaResultados, setMostrarGuiaResultados]);

  if (!mostrarGuiaResultados) return null;

  const irA = (p: "plan" | "vista3d" | "comparar" | "analisis") => {
    setPestania(p);
    setVistaMovil("trabajo");
    setMostrarGuiaResultados(false);
  };

  return (
    <div className="modal-fondo" role="dialog" aria-modal="true" aria-labelledby="modal-res-titulo">
      <div className="modal-caja modal-resultados">
        <div className="modal-res-cabecera">
          <div className="modal-res-insignia">
            <span className="punto-verde" /> Análisis listo
          </div>
          <button
            className="btn texto chico modal-res-cerrar"
            onClick={() => setMostrarGuiaResultados(false)}
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>

        <h3 id="modal-res-titulo">Tu campo analizado con datos de la NASA y del MGAP</h3>
        <p className="modal-res-bajada">
          Cruzamos el historial y las secciones de tu campo con 35 años de datos agroclimáticos de la NASA (NASA POWER y la lluvia de GPM IMERG),
          relieve SRTM y los suelos oficiales del MGAP.
        </p>

        <div className="modal-res-pistas">
          <h4>¿Qué mirar ahora y cómo navegar los resultados?</h4>
          <div className="modal-res-grilla">
            <button type="button" className="modal-res-tarjeta" onClick={() => irA("plan")}>
              <div className="modal-res-icono" aria-hidden>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
                  <line x1="8" y1="2" x2="8" y2="18" />
                  <line x1="16" y1="6" x2="16" y2="22" />
                </svg>
              </div>
              <div>
                <b>1. Tu campo, lote por lote</b>
                <span>{campo.sistema?.tipo === "ganadero" ? "Arranca en la opción sugerida. Tocá cada potrero para ver las otras opciones, con su porqué, y elegí vos." : "Arranca en la opción sugerida. Tocá cada lote para ver las otras opciones, con su porqué, y elegí vos."}</span>
              </div>
            </button>

            <button type="button" className="modal-res-tarjeta" onClick={() => irA("vista3d")}>
              <div className="modal-res-icono" aria-hidden>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m8 3 4 8 5-5 5 15H2L8 3z" />
                </svg>
              </div>
              <div>
                <b>2. Tu campo en 3D (NASA SRTM)</b>
                <span>Maqueta 3D que gira sola con el relieve real, pendientes y escurrimientos.</span>
              </div>
            </button>

            <button type="button" className="modal-res-tarjeta" onClick={() => irA("comparar")}>
              <div className="modal-res-icono" aria-hidden>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="20" x2="18" y2="10" />
                  <line x1="12" y1="20" x2="12" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="14" />
                </svg>
              </div>
              <div>
                <b>3. Comparar con alternativas</b>
                <span>Revisá márgenes brutos estimados y opciones con menor erosión o riesgo.</span>
              </div>
            </button>

            <button type="button" className="modal-res-tarjeta" onClick={() => irA("analisis")}>
              <div className="modal-res-icono" aria-hidden>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
              </div>
              <div>
                <b>4. Datos de suelo y clima</b>
                <span>Detalle de grupos CONEAT, balance de agua mensual y lluvias históricas.</span>
              </div>
            </button>
          </div>
        </div>

        {/* «Seguir conversando» se sacó: solo cerraba este cartel y detrás ya estaba la solución, así
            que parecía que abría la solución. El chat se abre cuando se quiera con «Preguntar». */}
        <div className="modal-res-pie" style={{ justifyContent: "flex-end" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <button type="button" className="btn" onClick={() => irA("vista3d")}>
              Explorar en 3D
            </button>
            <button type="button" className="btn primario" onClick={() => irA("plan")}>
              Ver mi campo y elegir →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
