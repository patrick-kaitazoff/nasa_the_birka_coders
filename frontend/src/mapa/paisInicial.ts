/** Con qué país abre el mapa cuando todavía no hay campo.
 *
 * En orden: ?pais=us|uy en el link, lo que la persona eligió antes en el selector de la barra, lo que dijo la IP la
 * última vez y, si nunca se preguntó, la zona horaria (America/Montevideo → Uruguay). La zona horaria es instantánea y
 * casi siempre coincide; la IP llega después (/api/pais, la cabecera de Vercel) y corrige si hace falta, solo si la
 * persona no tocó nada todavía. En la PC el servidor no sabe la IP y queda la zona horaria. */
export type Pais = "UY" | "US";

const ELEGIDO = "fieldshift.pais";
const POR_IP = "fieldshift.paisIP";

const leer = (k: string): Pais | null => {
  try {
    const v = localStorage.getItem(k);
    return v === "UY" || v === "US" ? v : null;
  } catch {
    return null;
  }
};
const escribir = (k: string, v: Pais) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* sin almacenamiento */
  }
};

function delLink(): Pais | null {
  const p = new URLSearchParams(location.search).get("pais")?.toLowerCase();
  return p === "us" ? "US" : p === "uy" ? "UY" : null;
}

function porZonaHoraria(): Pais {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone === "America/Montevideo" ? "UY" : "US";
  } catch {
    return "UY";
  }
}

export function paisInicial(): Pais {
  return delLink() ?? leer(ELEGIDO) ?? leer(POR_IP) ?? porZonaHoraria();
}

/** La persona eligió un país en la barra: manda sobre la IP de acá en adelante. */
export function elegirPais(p: Pais) {
  escribir(ELEGIDO, p);
}

/** Pregunta la IP y llama a `aplicar` si cambia lo que se adivinó. No hace nada si el país vino en el link o ya lo
 * eligió la persona. Uruguay es Uruguay; cualquier otro país, EE. UU. (el único otro con datos de suelo cargados). */
export async function corregirPorIP(aplicar: (p: Pais) => void) {
  if (delLink() || leer(ELEGIDO)) return;
  try {
    const r = await fetch("/api/pais", { cache: "no-store" });
    if (!r.ok) return;
    const { pais } = (await r.json()) as { pais: string | null };
    if (!pais) return;
    const p: Pais = pais === "UY" ? "UY" : "US";
    escribir(POR_IP, p);
    if (!leer(ELEGIDO)) aplicar(p);
  } catch {
    /* sin red: queda lo adivinado */
  }
}
