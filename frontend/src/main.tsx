import { StrictMode } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./estilos.css";
import "./tema-b.css"; // estética B (crema, lima y oliva), la misma de la portada
import { iniciarTraduccion } from "./i18n/observador";
import { vieneDePortada } from "./inicio/llegada";
import { useApp, crearSeccion, pidioDeCero } from "./store";
import { conectarHistorial } from "./comun/historial";

if (import.meta.env.DEV) {
  (window as any).useApp = useApp;
  (window as any).crearSeccion = crearSeccion;
}

iniciarTraduccion();
// se lee la marca de la portada al arrancar, así no queda para una recarga posterior
vieneDePortada();
// si la portada armó la página por adelantado, lo guardado ya se cargó: al mostrarse, si se pidió arrancar de cero,
// se vacía (va antes que el resto de lo que espera a mostrarse, porque se registra primero)
if ((document as Document & { prerendering?: boolean }).prerendering) {
  document.addEventListener("prerenderingchange", () => { if (pidioDeCero()) useApp.getState().nuevoCampo(); }, { once: true });
}
// «atrás» y «adelante» del navegador recorren las partes de la herramienta
conectarHistorial();

// El primer render va sincrónico: así, al llegar desde la portada, el primer cuadro que pinta el navegador (y el
// que usa para el fundido entre páginas) ya tiene la bienvenida, y no la página vacía. Ver
// «app-espera-al-codigo» en vite.config.ts.
const raiz = createRoot(document.getElementById("root")!);
flushSync(() =>
  raiz.render(
    <StrictMode>
      <App />
    </StrictMode>,
  ),
);
