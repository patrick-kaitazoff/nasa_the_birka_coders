/** Íconos y tramas de cada cultivo. Dibujados a mano, simples, para leer a tamaño chico. */

const OSCURO: Record<string, string> = {};

function oscurecer(hex: string, f = 0.62): string {
  if (OSCURO[hex + f]) return OSCURO[hex + f];
  const n = parseInt(hex.replace("#", ""), 16);
  const r = Math.round(((n >> 16) & 255) * f);
  const g = Math.round(((n >> 8) & 255) * f);
  const b = Math.round((n & 255) * f);
  const s = `rgb(${r},${g},${b})`;
  OSCURO[hex + f] = s;
  return s;
}

export function IconoCultivo({ icono, color, size = 18 }: { icono: string; color: string; size?: number }) {
  const t = oscurecer(color, 0.55);
  const comun = { width: size, height: size, viewBox: "0 0 24 24", "aria-hidden": true } as const;
  switch (icono) {
    case "soja":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          <path d="M12 19V8" stroke={t} strokeWidth="1.6" strokeLinecap="round" />
          <ellipse cx="8.6" cy="9.5" rx="2.4" ry="3.6" transform="rotate(-25 8.6 9.5)" fill="#fff" opacity=".85" />
          <ellipse cx="15.4" cy="11.5" rx="2.4" ry="3.6" transform="rotate(25 15.4 11.5)" fill="#fff" opacity=".85" />
        </svg>
      );
    case "maiz":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          <ellipse cx="12" cy="11" rx="3.4" ry="6.2" fill="#fff6c8" />
          <path d="M9.4 9h5.2M9 11.4h6M9.4 13.8h5.2" stroke={t} strokeWidth="1" />
          <path d="M8 18c1-2 2.5-3 4-3s3 1 4 3" stroke="#3f7d2a" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </svg>
      );
    case "trigo":
    case "cebada":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          <path d="M12 20V6" stroke={t} strokeWidth="1.5" strokeLinecap="round" />
          {[7.5, 10.5, 13.5].map((y) => (
            <g key={y} fill="#fff8de">
              <ellipse cx="9.9" cy={y} rx="1.5" ry="2.4" transform={`rotate(-30 9.9 ${y})`} />
              <ellipse cx="14.1" cy={y} rx="1.5" ry="2.4" transform={`rotate(30 14.1 ${y})`} />
            </g>
          ))}
        </svg>
      );
    case "colza":
    case "girasol":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          {[0, 60, 120, 180, 240, 300].map((a) => (
            <ellipse key={a} cx="12" cy="7.2" rx="2.1" ry="3.2" fill="#fffbe0" transform={`rotate(${a} 12 12)`} />
          ))}
          <circle cx="12" cy="12" r={icono === "girasol" ? 3.4 : 2.2} fill={icono === "girasol" ? "#6b3e12" : t} />
        </svg>
      );
    case "sorgo":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          <path d="M12 20v-8" stroke="#fff3e3" strokeWidth="1.5" strokeLinecap="round" />
          {[[12, 6], [9.8, 8], [14.2, 8], [10.4, 10.4], [13.6, 10.4], [12, 9]].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="1.7" fill="#ffe2c2" />
          ))}
        </svg>
      );
    case "pradera":
    case "verdeo":
    case "campo":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          <path d="M6 17c1-4 2-6 3-8M10 17c.5-4 1-7 2-10M14 17c0-3 .5-6 2-8M18 17c-.3-2.5-1-4.5-2.2-6" stroke="#eaffea" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          {icono === "pradera" && <circle cx="16.5" cy="7.5" r="1.9" fill="#fff" opacity=".9" />}
        </svg>
      );
    case "alfalfa":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          {[0, 120, 240].map((a) => (
            <circle key={a} cx="12" cy="8.6" r="2.9" fill="#f1e2ff" transform={`rotate(${a} 12 12)`} />
          ))}
          <circle cx="12" cy="12" r="1.3" fill={t} />
        </svg>
      );
    case "cobertura":
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          <path d="M12 19v-7" stroke="#eafff4" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M12 12c-1-3-3.5-4.5-6-4.5 0 3 2.5 5 6 4.5zM12 13c1-3 3.5-4.5 6-4.5 0 3-2.5 5-6 4.5z" fill="#eafff4" />
        </svg>
      );
    case "barbecho":
    default:
      return (
        <svg {...comun}>
          <circle cx="12" cy="12" r="11" fill={color} />
          <path d="M5.5 10h4M12 10h6M7 14h6M15 14h3M6 18h3" stroke={t} strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
  }
}

/** Tramas SVG para pintar cada cultivo en el mapa del plan (se distinguen también en blanco y negro). */
export function definicionesTramas(cultivos: Array<{ codigo: string; color: string; icono: string }>) {
  return cultivos.map((c) => {
    const id = `trama-${c.codigo}`;
    const t = oscurecer(c.color, 0.6);
    let dibujo: React.ReactNode;
    switch (c.icono) {
      case "soja":
        dibujo = <><circle cx="3" cy="3" r="1.5" fill={t} /><circle cx="9" cy="9" r="1.5" fill={t} /></>;
        break;
      case "maiz":
        dibujo = <path d="M3 0v12M9 0v12" stroke={t} strokeWidth="1.6" />;
        break;
      case "trigo":
      case "cebada":
        dibujo = <path d="M0 12L12 0M-3 3l6-6M9 15l6-6" stroke={t} strokeWidth="1.4" />;
        break;
      case "colza":
      case "girasol":
        dibujo = <path d="M3 6h6M6 3v6" stroke={t} strokeWidth="1.4" />;
        break;
      case "sorgo":
        dibujo = <path d="M0 0L12 12M-3 9l6 6M9 -3l6 6" stroke={t} strokeWidth="1.4" />;
        break;
      case "pradera":
      case "campo":
      case "verdeo":
        dibujo = <path d="M2 10c.5-2 1-3 2-4M5 10c0-2 .3-3 1-4.5M8.5 10c-.2-1.6-.6-2.8-1.4-3.6" stroke={t} strokeWidth="1.1" fill="none" />;
        break;
      case "alfalfa":
        dibujo = <><circle cx="6" cy="6" r="2.2" fill="none" stroke={t} strokeWidth="1.2" /></>;
        break;
      case "cobertura":
        dibujo = <path d="M3 3l2 2M5 3L3 5M9 8l2 2M11 8l-2 2" stroke={t} strokeWidth="1.2" />;
        break;
      default:
        dibujo = <path d="M1 4h4M7 9h4" stroke={t} strokeWidth="1.2" strokeLinecap="round" />;
    }
    return (
      <pattern key={id} id={id} width="12" height="12" patternUnits="userSpaceOnUse">
        <rect width="12" height="12" fill={c.color} />
        {dibujo}
      </pattern>
    );
  });
}

export function MarcaFieldShift({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <rect width="64" height="64" rx="14" fill="#1F4D3A" />
      <path d="M10 44 L54 44" stroke="#C9A227" strokeWidth="4" strokeLinecap="round" />
      <path d="M14 36 Q32 18 50 36" fill="none" stroke="#9BD3AE" strokeWidth="4" strokeLinecap="round" />
      <circle cx="44" cy="17" r="5" fill="#F2C80F" />
    </svg>
  );
}
