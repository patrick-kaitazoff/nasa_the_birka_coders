/** Botón «Leer en voz alta» debajo de cada respuesta del asesor, como en ChatGPT.
 *
 * Usa la voz del navegador (Web Speech API): no cuesta nada, no manda el texto a ningún servidor y anda sin
 * clave. Lee lo que se ve en la pantalla (innerText), así en inglés lee la traducción. La calidad de la voz
 * depende del navegador y del sistema (Chrome y Edge traen voces buenas en castellano; Safari usa las de
 * macOS/iOS). Si el navegador no tiene voz, el botón no aparece.
 *
 * Detalles:
 * - Se lee de a frases (hasta ~180 letras por tramo): Chrome corta una lectura larga a los ~15 segundos.
 * - Una sola lectura a la vez: tocar otro mensaje corta la anterior; tocar el mismo, la detiene. */
import { useEffect, type RefObject } from "react";
import { create } from "zustand";
import { useIdioma } from "../i18n/idioma";

const useLectura = create<{ id: string | null; poner: (id: string | null) => void }>((set) => ({
  id: null,
  poner: (id) => set({ id }),
}));

const hayVoz = () => typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

/** Las abreviaturas que la voz lee mal («t/ha» sonaba «te barra ha»). */
const UNIDADES: Record<"es" | "en", Array<[RegExp, string]>> = {
  es: [
    [/t\/ha\/año/g, "toneladas por hectárea por año"],
    [/t\/ha/g, "toneladas por hectárea"],
    [/kg\/ha/g, "kilos por hectárea"],
    [/USD\/ha/g, "dólares por hectárea"],
    [/USD/g, "dólares"],
    [/(\d)\s?ha\b/g, "$1 hectáreas"],
    [/(\d)\s?mm\b/g, "$1 milímetros"],
    [/°C/g, " grados"],
    [/(\d)ª/g, "$1"],
    [/→/g, ", después,"],
  ],
  en: [
    [/t\/ha\/(año|year)/g, "tonnes per hectare per year"],
    [/t\/ha/g, "tonnes per hectare"],
    [/kg\/ha/g, "kilograms per hectare"],
    [/USD\/ha/g, "dollars per hectare"],
    [/(\d)\s?ha\b/g, "$1 hectares"],
    [/(\d)\s?mm\b/g, "$1 millimetres"],
    [/°C/g, " degrees"],
    [/→/g, ", then,"],
  ],
};

export function textoParaLeer(t: string, idioma: "es" | "en"): string {
  let s = t.replace(/[*#_`]/g, "").replace(/\s*\n+\s*/g, ". ").replace(/\.\s*\./g, ".");
  for (const [re, por] of UNIDADES[idioma]) s = s.replace(re, por);
  return s.replace(/\s{2,}/g, " ").trim();
}

export function trozos(t: string, max = 180): string[] {
  const frases = t.split(/(?<=[.!?;:])\s+/);
  const out: string[] = [];
  for (const f of frases) {
    const ultimo = out[out.length - 1];
    if (ultimo && ultimo.length + f.length + 1 <= max) out[out.length - 1] = `${ultimo} ${f}`;
    else out.push(f);
  }
  return out.filter((x) => x.trim());
}

const PREFERIDAS = {
  es: ["es-UY", "es-AR", "es-419", "es-US", "es-MX", "es-ES"],
  en: ["en-US", "en-GB", "en-AU"],
};

function elegirVoz(idioma: "es" | "en"): SpeechSynthesisVoice | null {
  const voces = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(idioma));
  if (!voces.length) return null;
  const orden = (v: SpeechSynthesisVoice) => {
    const i = PREFERIDAS[idioma].findIndex((l) => v.lang.toLowerCase() === l.toLowerCase());
    const buena = /natural|neural|google|premium|enhanced/i.test(v.name) ? 0 : 1;
    return (i < 0 ? 50 : i) * 2 + buena;
  };
  return [...voces].sort((a, b) => orden(a) - orden(b))[0];
}

function IconoParlante() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  );
}

function IconoDetener() {
  return (
    <span className="leer-ondas" aria-hidden>
      <i /><i /><i /><i />
    </span>
  );
}

export function BotonLeer({ id, origen }: { id: string; origen: RefObject<HTMLElement | null> }) {
  const leyendo = useLectura((s) => s.id);
  const poner = useLectura((s) => s.poner);
  const idioma = useIdioma((s) => s.idioma);
  const activo = leyendo === id;

  // las voces cargan solas al rato de abrir la página: se piden de entrada para que el primer toque ya las tenga
  useEffect(() => {
    if (hayVoz()) window.speechSynthesis.getVoices();
  }, []);

  if (!hayVoz()) return null;

  function alternar() {
    const voz = window.speechSynthesis;
    voz.cancel();
    if (activo) {
      poner(null);
      return;
    }
    const texto = textoParaLeer(origen.current?.innerText || "", idioma);
    const partes = trozos(texto);
    if (!partes.length) return;
    const elegida = elegirVoz(idioma);
    poner(id);
    const terminar = () => {
      if (useLectura.getState().id === id) poner(null);
    };
    partes.forEach((p, i) => {
      const u = new SpeechSynthesisUtterance(p);
      u.lang = elegida?.lang || (idioma === "en" ? "en-US" : "es-419");
      if (elegida) u.voice = elegida;
      u.onerror = terminar; // también llega al cortarla: si ya se está leyendo otro mensaje, no hace nada
      if (i === partes.length - 1) u.onend = terminar;
      voz.speak(u);
    });
  }

  return (
    <button
      type="button"
      className={`btn-leer ${activo ? "on" : ""}`}
      onClick={alternar}
      aria-label={activo ? "Detener la lectura" : "Leer en voz alta"}
      title={activo ? "Detener la lectura" : "Leer en voz alta"}
      aria-pressed={activo}
    >
      {activo ? <IconoDetener /> : <IconoParlante />}
    </button>
  );
}
