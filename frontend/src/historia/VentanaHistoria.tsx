import { useEffect, useRef } from "react";
import { useApp } from "../store";
import { HistoriaDetalle } from "./Historia";

/**
 * Ventana «Tu campo, temporada por temporada», encima de Plan (o de la pestaña en que se abra).
 * Se cierra con Escape, con la cruz o tocando afuera, y devuelve el foco al botón que la abrió.
 */
export function VentanaHistoria() {
  const { historiaAbierta, cerrarHistoria } = useApp();
  const abridor = useRef<HTMLElement | null>(null);
  const cruz = useRef<HTMLButtonElement>(null);
  const abierta = !!historiaAbierta;

  useEffect(() => {
    if (!abierta) return;
    abridor.current = document.activeElement as HTMLElement | null;
    cruz.current?.focus();
    const alTecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") cerrarHistoria();
    };
    window.addEventListener("keydown", alTecla);
    return () => {
      window.removeEventListener("keydown", alTecla);
      abridor.current?.focus?.();
    };
  }, [abierta, cerrarHistoria]);

  if (!historiaAbierta) return null;

  return (
    <div className="modal-fondo modal-fondo-historia" onClick={cerrarHistoria} role="dialog" aria-modal="true" aria-labelledby="ventana-historia-titulo">
      <div className="modal-caja modal-historia" onClick={(e) => e.stopPropagation()}>
        <div className="modal-historia-cabecera">
          <div>
            <h2 id="ventana-historia-titulo">Tu campo, temporada por temporada</h2>
            <p className="bajada">
              Desde el año 2000, con el clima diario de la NASA (NASA POWER y la lluvia de GPM IMERG) y el verdor del satélite (MODIS): qué se hizo, qué habría pasado con este plan y cuánto coincide la app con lo que vio el satélite.
            </p>
          </div>
          <button ref={cruz} className="btn chico fantasma" onClick={cerrarHistoria} aria-label="Cerrar ventana" style={{ fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>
        <div className="modal-historia-cuerpo">
          <HistoriaDetalle seccionInicial={historiaAbierta.seccion} temporadaInicial={historiaAbierta.temporada} />
        </div>
      </div>
    </div>
  );
}
