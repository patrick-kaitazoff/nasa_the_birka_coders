/** País del campo en la barra de arriba, al lado de ES | EN. Antes era una fila «El campo está en: Uruguay · Estados Unidos»
 * dentro de la tarjeta del paso 1 y alargaba la tarjeta hasta cortarla. El país arranca solo (store.ts: ?pais=, lo
 * elegido antes, la IP o la zona horaria); esto es para cambiarlo. Se ve mientras no hay campo marcado: después el
 * país lo dice el campo.
 *
 * Las banderas van dibujadas: Windows no muestra los emojis de banderas (sale «UY» en letras). */
import { useEffect, useRef, useState } from "react";
import { useApp } from "../store";
import { elegirPais } from "./paisInicial";

type Pais = "UY" | "US";

function BanderaUY() {
  return (
    <svg className="bandera" viewBox="0 0 27 18" aria-hidden>
      <rect width="27" height="18" fill="#fff" />
      {[2, 6, 10, 14].map((y) => <rect key={y} y={y} width="27" height="2" fill="#0038a8" />)}
      <rect width="13" height="10" fill="#fff" />
      <circle cx="6.5" cy="5" r="2.6" fill="#fcd116" stroke="#7b3f00" strokeWidth="0.4" />
    </svg>
  );
}

function BanderaUS() {
  return (
    <svg className="bandera" viewBox="0 0 26 18" aria-hidden>
      <rect width="26" height="18" fill="#fff" />
      {[0, 2.77, 5.54, 8.31, 11.08, 13.85, 16.62].map((y) => <rect key={y} y={y} width="26" height="1.38" fill="#b22234" />)}
      <rect width="11" height="9.7" fill="#3c3b6e" />
    </svg>
  );
}

const PAISES: Array<{ id: Pais; nombre: string; Bandera: typeof BanderaUY }> = [
  { id: "UY", nombre: "Uruguay", Bandera: BanderaUY },
  { id: "US", nombre: "Estados Unidos", Bandera: BanderaUS },
];

export function SelectorPais() {
  const { paisMapa, setPaisMapa, campo, esEjemplo } = useApp();
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => { if (!caja.current?.contains(e.target as Node)) setAbierto(false); };
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") setAbierto(false); };
    window.addEventListener("mousedown", fuera);
    window.addEventListener("keydown", tecla);
    return () => { window.removeEventListener("mousedown", fuera); window.removeEventListener("keydown", tecla); };
  }, [abierto]);

  if (campo.contorno || esEjemplo) return null;
  const actual = PAISES.find((p) => p.id === paisMapa) ?? PAISES[0];

  return (
    <div className="selector-pais" ref={caja}>
      <button
        type="button"
        className="selector-pais-btn"
        onClick={() => setAbierto(!abierto)}
        aria-haspopup="listbox"
        aria-expanded={abierto}
        title="País del campo: cambia el mapa y las formas de ubicarlo"
      >
        <actual.Bandera />
        <span>{actual.nombre}</span>
        <span className="campo-nombre-flecha" aria-hidden>▾</span>
      </button>
      {abierto && (
        <div className="menu-campo-dropdown selector-pais-menu" role="listbox" aria-label="País del campo">
          {PAISES.map((p) => (
            <button
              key={p.id}
              type="button"
              role="option"
              aria-selected={p.id === paisMapa}
              className={`menu-campo-item ${p.id === paisMapa ? "elegido" : ""}`}
              onClick={() => { elegirPais(p.id); setPaisMapa(p.id); setAbierto(false); }}
            >
              <p.Bandera />
              <span>{p.nombre}</span>
              {p.id === paisMapa && <span className="selector-pais-tilde" aria-hidden>✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
