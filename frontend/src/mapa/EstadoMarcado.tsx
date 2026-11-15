import { useApp } from "../store";

/** Cuántas esquinas lleva y qué superficie encierra lo que se está marcando, con deshacer y cancelar. */
export function EstadoMarcado({ que, circulo }: { que: "campo" | "seccion"; circulo?: boolean }) {
  const { marcando } = useApp();
  if (!marcando) return null;
  const { puntos, ha } = marcando;
  const fmt = (x: number) => x.toLocaleString("es-UY", { maximumFractionDigits: x < 10 ? 1 : 0 });
  if (circulo) {
    return (
      <div className="estado-marcado" aria-live="polite">
        <span>
          {ha <= 0 ? "Tocá el centro del pivot y arrastrá hasta el borde."
            : <>Radio marcado · <b>{`unas ${fmt(ha)} ha`}</b>. Soltá para confirmar.</>}
        </span>
        <button className="btn texto chico" onClick={() => window.dispatchEvent(new Event("fieldshift:cancelar-dibujo"))}>Cancelar (Esc)</button>
      </div>
    );
  }
  return (
    <div className="estado-marcado" aria-live="polite">
      <span>
        {/* frases enteras, no armadas con pedazos: en inglés el pedazo («lote») quedaba sin traducir */}
        {puntos === 0 ? (que === "campo" ? "Tocá la primera esquina del campo." : useApp.getState().campo.sistema?.tipo === "ganadero" ? "Tocá la primera esquina del potrero." : "Tocá la primera esquina del lote.")
          : puntos === 1 ? "1 esquina: seguí marcando."
          : puntos < 3 ? `${puntos} esquinas: seguí marcando.`
          : <>{puntos} esquinas · <b>{`unas ${fmt(ha)} ha`}</b>. Para cerrar, tocá la primera.</>}
      </span>
      {puntos > 0 && (
        <div style={{ display: "inline-flex", gap: 6, marginLeft: 6 }}>
          <button className="btn texto chico" onClick={() => window.dispatchEvent(new Event("fieldshift:borrar-punto"))}>Deshacer punto</button>
          <button className="btn texto chico" onClick={() => window.dispatchEvent(new Event("fieldshift:cancelar-dibujo"))}>Cancelar (Esc)</button>
        </div>
      )}
    </div>
  );
}
