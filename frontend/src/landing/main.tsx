import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Landing } from "./Landing";
import "./landing.css";
import { useIdioma } from "../i18n/idioma";

// Portada A, en «/»; la B quedó en /b. La herramienta estaba en «/»: los links con sus parámetros (campo de ejemplo, puente,
// pestaña, campo vacío) siguen andando y van a /app con lo mismo.
const q = new URLSearchParams(location.search);
if (["demo", "puente", "pestania", "vacio"].some((k) => q.has(k))) {
  location.replace("/app" + location.search + location.hash);
} else {
  const mostrar = () =>
    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <Landing />
      </StrictMode>,
    );
  // El traductor trae los diccionarios (~130 KB). En castellano la portada no lo necesita para mostrarse: se
  // baja después, por si se toca EN. En inglés se espera, para no mostrar el castellano un instante.
  const traductor = () => import("../i18n/observador").then((m) => m.iniciarTraduccion());
  if (useIdioma.getState().idioma === "en") traductor().catch(() => undefined).finally(mostrar);
  else {
    mostrar();
    traductor().catch(() => undefined);
  }
}
