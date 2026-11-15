import { useLayoutEffect, useRef, useState } from "react";
import { PlanoSVG } from "./PlanoSVG";
import type { Geo, Seccion } from "../tipos";

/** El plano del campo ocupando todo su recuadro, dibujado al tamaño real del recuadro (no estirado), así los rótulos
 * se leen a su tamaño. Es la vista principal del Plan; reemplaza al mapa satelital. */
export function PlanoAjustado(props: {
  contorno: Geo;
  secciones: Seccion[];
  cultivoDe: (seccionId: string) => string | undefined;
  info: (cod: string) => { color: string; icono: string; nombre: string };
  seleccion?: string | null;
  onSeccion?: (id: string) => void;
}) {
  const caja = useRef<HTMLDivElement>(null);
  const [tam, setTam] = useState<{ w: number; h: number } | null>(null);
  useLayoutEffect(() => {
    const el = caja.current;
    if (!el) return;
    const medir = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 40 && r.height > 40) setTam({ w: Math.floor(r.width), h: Math.floor(r.height) });
    };
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={caja} className="plano-ajustado">
      {tam && <PlanoSVG {...props} W={tam.w} H={tam.h} norteAbajo />}
    </div>
  );
}
