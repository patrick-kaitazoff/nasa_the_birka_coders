import L from "leaflet";

export interface Etiqueta {
  marcador: L.Marker;
  peso: number; // las de más peso (secciones más grandes) se muestran primero
}

/** Oculta las etiquetas que se pisan con otra de más peso. Se vuelve a correr al hacer zoom. */
export function desencimar(lista: Etiqueta[]) {
  const puestas: DOMRect[] = [];
  for (const e of [...lista].sort((a, b) => b.peso - a.peso)) {
    const el = e.marcador.getElement()?.firstElementChild as HTMLElement | null;
    if (!el) continue;
    el.style.visibility = "visible";
    const r = el.getBoundingClientRect();
    const choca = puestas.some((p) => !(r.right + 4 < p.left || r.left - 4 > p.right || r.bottom + 2 < p.top || r.top - 2 > p.bottom));
    if (choca) el.style.visibility = "hidden";
    else puestas.push(r);
  }
}

export function etiquetaHTML(texto: string, detalle: string, color?: string) {
  const punto = color ? `<span style="width:10px;height:10px;border-radius:3px;background:${color};display:inline-block"></span>` : "";
  return `<div class="etiqueta-mapa">${punto}${texto} <small>${detalle}</small></div>`;
}
