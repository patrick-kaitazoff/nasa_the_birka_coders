import type { ReactNode } from "react";
import { useApp } from "../store";
import { idTermino } from "./Glosario";

/** Marca y lleva a un bloque de Datos un momento, para que se vea adónde llevó el índice o el hallazgo. */
export function resaltar(el: Element | null) {
  if (!el) return;
  el.classList.remove("datos-resaltado");
  void (el as HTMLElement).offsetWidth; // reinicia la animación si ya estaba
  el.classList.add("datos-resaltado");
  window.setTimeout(() => el.classList.remove("datos-resaltado"), 1800);
}

/** Lleva hasta un elemento de la pestaña Datos (después de que React pinte lo que se haya desplegado). */
export function irA(id: string, bloque: ScrollLogicalPosition = "start") {
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      const el = document.getElementById(id);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: bloque });
      resaltar(el);
    }),
  );
}

/**
 * Una palabra del glosario dentro de un texto de Datos: al tocarla se abre «Para el agrónomo», se despliega
 * su explicación y se baja hasta ella. Va solo donde el texto ya nombra el término.
 */
export function Termino({ t, children }: { t: string; children: ReactNode }) {
  const setDatosAgronomo = useApp((s) => s.setDatosAgronomo);
  return (
    <button
      type="button"
      className="termino"
      title="Ver qué quiere decir"
      onClick={() => {
        setDatosAgronomo(true);
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            const d = document.getElementById(idTermino(t)) as HTMLDetailsElement | null;
            if (!d) return;
            d.open = true;
            d.scrollIntoView({ behavior: "smooth", block: "center" });
            resaltar(d);
          }),
        );
      }}
    >
      {children}
    </button>
  );
}
