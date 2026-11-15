/** Las sugerencias del chat en una sola fila que se desliza de costado.
 *
 * Envueltas en varias líneas, en la pantalla de la compu (~1100 × 550)
 * cinco sugerencias ocupaban cuatro renglones, achicaban la charla a la mitad y cortaban la tarjeta o el saludo de
 * arriba. Ahora van en una fila: la rueda del mouse también la desliza, y un degradé en el borde avisa que hay más. */
import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";

/** También la usan las capas del relieve 3D en el recuadro chico del Plan (`className="vista3d-capas"`). */
export function FilaSugerencias({ children, className = "", ...resto }: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  const fila = useRef<HTMLDivElement>(null);
  const [mas, setMas] = useState({ izq: false, der: false });
  const ultimo = useRef({ izq: false, der: false });

  useEffect(() => {
    const el = fila.current;
    if (!el) return;
    // Solo cambia el estado si cambió algo. Antes ponía un objeto nuevo en cada medida, y como este efecto
    // corre en cada dibujo del chat (los hijos son un arreglo nuevo cada vez), cada letra escrita en el casillero
    // sumaba otro dibujo. Escribiendo rápido React cortaba con «Maximum update depth exceeded» (error 185) y la letra
    // se perdía («quieroseguir», «catte» en la prueba de los dos casos).
    // Ni siquiera se llama a setMas si no cambió: React cuenta como «actualización anidada» cualquier cambio de estado
    // que quede pendiente al terminar de dibujar, aunque después no cambie nada, y a las 50 seguidas corta.
    const medir = () => {
      const izq = el.scrollLeft > 2, der = el.scrollLeft + el.clientWidth < el.scrollWidth - 2;
      if (ultimo.current.izq === izq && ultimo.current.der === der) return;
      ultimo.current = { izq, der };
      setMas({ izq, der });
    };
    // la rueda vertical desliza la fila (con mouse no hay rueda de costado); si la fila ya llegó al borde, la rueda
    // sigue de largo y mueve la charla
    const rueda = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY) || el.scrollWidth <= el.clientWidth) return;
      const antes = el.scrollLeft;
      el.scrollLeft += e.deltaY;
      if (el.scrollLeft !== antes) e.preventDefault();
    };
    medir();
    el.addEventListener("scroll", medir, { passive: true });
    el.addEventListener("wheel", rueda, { passive: false });
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => { el.removeEventListener("scroll", medir); el.removeEventListener("wheel", rueda); ro.disconnect(); };
  }, [children]);

  return (
    <div ref={fila} {...resto} className={`sugerencias ${className} ${mas.izq ? "mas-izq" : ""} ${mas.der ? "mas-der" : ""}`}>
      {children}
    </div>
  );
}
