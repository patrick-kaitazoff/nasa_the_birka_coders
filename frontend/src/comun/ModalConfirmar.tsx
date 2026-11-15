import { useEffect, useRef } from "react";
import { useApp } from "../store";

/**
 * Modal de confirmación para comenzar de cero.
 * Reemplaza los window.confirm del navegador por un diálogo estilizado y accesible.
 */
export function ModalConfirmar() {
  const { confirmarNuevo, setConfirmarNuevo, nuevoCampo } = useApp();
  const botonCancelar = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirmarNuevo) {
      botonCancelar.current?.focus();
      const alTecla = (e: KeyboardEvent) => {
        if (e.key === "Escape") setConfirmarNuevo(false);
      };
      window.addEventListener("keydown", alTecla);
      return () => window.removeEventListener("keydown", alTecla);
    }
  }, [confirmarNuevo, setConfirmarNuevo]);

  if (!confirmarNuevo) return null;

  return (
    <div className="modal-fondo" onClick={() => setConfirmarNuevo(false)} role="dialog" aria-modal="true" aria-labelledby="modal-confirmar-titulo">
      <div className="modal-caja" onClick={(e) => e.stopPropagation()}>
        <div className="modal-cabecera">
          <div className="modal-icono" aria-hidden>!</div>
          <div>
            <h3 id="modal-confirmar-titulo">¿Empezar de nuevo?</h3>
            <p className="modal-texto">Se borrarán los datos del campo actual, la conversación y el análisis de este navegador.</p>
          </div>
        </div>
        <div className="modal-acciones">
          <button ref={botonCancelar} className="btn secundario" onClick={() => setConfirmarNuevo(false)}>
            Seguir con este campo
          </button>
          <button className="btn peligro" onClick={() => nuevoCampo()}>
            Empezar de nuevo
          </button>
        </div>
      </div>
    </div>
  );
}
