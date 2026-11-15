import { useIdioma } from "./idioma";
import "./selector-idioma.css";

/** Botón ES / EN de la barra de arriba. Los textos ES y EN no se traducen (data-no-traducir). */
export function SelectorIdioma() {
  const { idioma, setIdioma } = useIdioma();
  return (
    <div className="selector-idioma" role="group" aria-label="Idioma / Language" data-no-traducir>
      <button
        type="button"
        className={`opcion-idioma ${idioma === "es" ? "activa" : ""}`}
        aria-pressed={idioma === "es"}
        onClick={() => setIdioma("es")}
        title="Cambiar a Español"
      >
        ES
      </button>
      <span className="separador-idioma" aria-hidden>|</span>
      <button
        type="button"
        className={`opcion-idioma ${idioma === "en" ? "activa" : ""}`}
        aria-pressed={idioma === "en"}
        onClick={() => setIdioma("en")}
        title="Switch to English"
      >
        EN
      </button>
    </div>
  );
}
