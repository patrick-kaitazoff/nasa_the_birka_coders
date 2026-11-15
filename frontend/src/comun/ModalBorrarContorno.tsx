import { useEffect, useRef } from "react";
import { useApp } from "../store";

/**
 * Modal de confirmación para borrar el contorno del campo y empezar a marcarlo de nuevo.
 * Avisa claramente si se pierden lotes o análisis existentes.
 */
export function ModalBorrarContorno() {
  const { confirmarBorrarContorno, setConfirmarBorrarContorno, borrarContorno, campo, analisis, plan } = useApp();
  const botonCancelar = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirmarBorrarContorno) {
      botonCancelar.current?.focus();
      const alTecla = (e: KeyboardEvent) => {
        if (e.key === "Escape") setConfirmarBorrarContorno(false);
      };
      window.addEventListener("keydown", alTecla);
      return () => window.removeEventListener("keydown", alTecla);
    }
  }, [confirmarBorrarContorno, setConfirmarBorrarContorno]);

  if (!confirmarBorrarContorno) return null;

  const cantLotes = campo.secciones?.length || 0;
  const hayAnalisis = !!(analisis || plan);

  let mensaje = "Vas a borrar el contorno actual para poder marcarlo o cargarlo de nuevo.";
  if (cantLotes > 0 && hayAnalisis) {
    mensaje = `Si borrás el contorno también se borran los ${cantLotes} lotes y el análisis del campo. Vas a tener que marcar el campo de nuevo.`;
  } else if (cantLotes > 0) {
    mensaje = `Si borrás el contorno también se borran los ${cantLotes} lotes marcados, porque se recortan a sus límites. Vas a tener que marcar el campo de nuevo.`;
  } else if (hayAnalisis) {
    mensaje = "Si borrás el contorno se borran el análisis y el plan de este campo. Vas a tener que marcar el campo de nuevo.";
  }

  return (
    <div className="modal-fondo" onClick={() => setConfirmarBorrarContorno(false)} role="dialog" aria-modal="true" aria-labelledby="modal-borrar-contorno-titulo">
      <div className="modal-caja" onClick={(e) => e.stopPropagation()}>
        <div className="modal-cabecera">
          <div className="modal-icono" aria-hidden>!</div>
          <div>
            <h3 id="modal-borrar-contorno-titulo">¿Borrar el contorno y empezar de nuevo?</h3>
            <p className="modal-texto">{mensaje}</p>
          </div>
        </div>
        <div className="modal-acciones">
          <button ref={botonCancelar} className="btn secundario" onClick={() => setConfirmarBorrarContorno(false)}>
            Mantener contorno
          </button>
          <button className="btn peligro" onClick={() => borrarContorno()}>
            Sí, borrar contorno
          </button>
        </div>
      </div>
    </div>
  );
}
