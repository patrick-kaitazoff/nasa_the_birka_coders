import { useEffect, useRef, useState } from "react";
import { ThinkingOrb, type OrbState } from "thinking-orbs";

/**
 * Indicador de "estoy trabajando" con las esferas de puntos de thinking-orbs (MIT, Jakub Antalik), en vez
 * del círculo que gira. Cada espera tiene su animación:
 * - "buscando": un meridiano que barre un globo (bajar imágenes de la NASA, buscar el padrón, ubicarte)
 * - "calculando": partículas en órbita (el análisis)
 * - "escribiendo": una banda que ondula (el asistente arma la respuesta o el plan)
 * - "guardando": anillo respirando
 * Respeta "reducir movimiento" del sistema (queda quieto) y se pausa si no está a la vista.
 * Se asegura de reactivarse si nació oculta (por ejemplo en un acordeón o panel plegado).
 */
const ESTADO: Record<"buscando" | "calculando" | "escribiendo" | "guardando", OrbState> = {
  buscando: "searching",
  calculando: "working",
  escribiendo: "composing",
  guardando: "breathing",
};

export interface CargandoProps {
  que?: keyof typeof ESTADO;
  claro?: boolean;
  color?: string;
  size?: 20 | 32 | 64;
  etiqueta?: string;
  className?: string;
  style?: React.CSSProperties;
}

export function Cargando({
  que = "calculando",
  claro = false,
  color,
  size = 20,
  etiqueta,
  className = "",
  style,
}: CargandoProps) {
  const [activo, setActivo] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setActivo(true);
      return;
    }
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setActivo(true);
      }
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const st = ESTADO[que];
  // En tamaño 20 con "working", la librería baja la cantidad de partículas a 3 puntos sueltos.
  // Con dots=2.5 se completa la esfera de órbitas preservando el diseño.
  const dots = st === "working" && size === 20 ? 2.5 : 1;
  const colorFinal = color ?? (claro ? "#ffffff" : "#1f4d3a");

  return (
    <span
      ref={ref}
      className={`cargando-contenedor ${className}`.trim()}
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", verticalAlign: "middle", ...style }}
    >
      <ThinkingOrb
        key={activo ? "vis" : "ini"}
        state={st}
        size={size}
        dots={dots}
        theme={claro ? "dark" : "light"}
        color={colorFinal}
        className="cargando"
        style={{ display: "inline-block", verticalAlign: "middle" }}
        aria-label={etiqueta || "Cargando"}
      />
    </span>
  );
}
