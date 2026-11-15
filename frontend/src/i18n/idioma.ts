/** Idioma de la pantalla: "es" (el original) o "en". Se elige con el botón ES/EN de la barra; también
 * con ?lang=en en la URL (para la demo). Se recuerda en este navegador. */
import { create } from "zustand";

export type Idioma = "es" | "en";
const CLAVE = "fieldshift.idioma";

function inicial(): Idioma {
  const url = new URLSearchParams(location.search).get("lang");
  if (url === "en" || url === "es") return url;
  try {
    const guardado = localStorage.getItem(CLAVE);
    if (guardado === "en" || guardado === "es") return guardado;
  } catch {
    /* sin almacenamiento */
  }
  // Antes seguía el idioma del navegador, y en Uruguay
  // abría en castellano. El jurado de Space Apps lee en inglés; quien elige ES con el botón lo sigue viendo así.
  return "en";
}

export const useIdioma = create<{ idioma: Idioma; setIdioma: (i: Idioma) => void }>((set) => ({
  idioma: inicial(),
  setIdioma: (idioma) => {
    try {
      localStorage.setItem(CLAVE, idioma);
    } catch {
      /* sin almacenamiento */
    }
    set({ idioma });
  },
}));
