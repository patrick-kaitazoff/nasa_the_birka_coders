import type { EstadoTrigo } from "../landing/CampoTrigo";

/** Hasta dónde sube la cámara del trigo al tocar un botón de la portada: la bienvenida sigue subiendo hasta ahí, en
 * la misma dirección. */
export const VISTA_LLEGADA = 0.32;

/** La página se está armando por adelantado (la portada la pide con speculation rules) y todavía no se ve. */
export function armandoPorAdelantado(): boolean {
  return typeof document !== "undefined" && (document as Document & { prerendering?: boolean }).prerendering === true;
}

/** Si la herramienta se abrió desde un botón de la portada: la portada
 * deja una marca en sessionStorage y acá se lee una sola vez, así recargar /app no vuelve a hacer el vuelo. Si la
 * página se armó por adelantado, la marca recién existe cuando se muestra: hasta ahí no se lee. */
let llegada: boolean | null = null;
/** La foto del último cuadro del trigo de la portada (JPEG en data URL), o null. */
let foto: string | null = null;

export function vieneDePortada(): boolean {
  if (armandoPorAdelantado()) return false;
  if (llegada === null) {
    try {
      const t = Number(sessionStorage.getItem("fs:desdePortada") || 0);
      sessionStorage.removeItem("fs:desdePortada");
      llegada = t > 0 && Date.now() - t < 15000;
      // la foto se lee y se borra acá, aunque después no haya bienvenida (campo guardado): no queda ocupando lugar
      foto = sessionStorage.getItem("fs:fotoPortada");
      sessionStorage.removeItem("fs:fotoPortada");
      if (!llegada || !foto?.startsWith("data:image/")) foto = null;
    } catch {
      llegada = false;
    }
  }
  return llegada;
}

/** La foto con la que se fue la portada: la bienvenida la muestra de fondo durante el fundido y
 * recién después arranca su propio trigo 3D encima, desde ese mismo cuadro. Armar el trigo en pleno fundido era lo
 * que lo trababa. */
export function fotoDePortada(): string | null {
  return vieneDePortada() ? foto : null;
}

/** Cómo dejó la portada el trigo al irse. Se lee una vez y queda guardado (React puede llamar dos veces). */
let escena: EstadoTrigo | null | undefined;

export function estadoDePortada(): EstadoTrigo | null {
  if (!vieneDePortada()) return null;
  if (escena === undefined) {
    try {
      const v = sessionStorage.getItem("fs:vistaPortada");
      sessionStorage.removeItem("fs:vistaPortada");
      const e = v ? (JSON.parse(v) as EstadoTrigo) : null;
      escena = e && Number.isFinite(e.vista) ? e : null;
    } catch {
      escena = null;
    }
  }
  return escena;
}

/** Si la página se armó por adelantado, avisa cuando se muestra de verdad (ahí ya se tocó el botón). */
export function alMostrarse(fn: () => void): () => void {
  if (!armandoPorAdelantado()) return () => {};
  const cb = () => fn();
  document.addEventListener("prerenderingchange", cb, { once: true });
  return () => document.removeEventListener("prerenderingchange", cb);
}

/** Se cumple cuando terminó el fundido entre la portada y esta página, o enseguida si no hubo fundido.
 * Con «Ver un campo de ejemplo», armar el Plan por detrás ocupaba el procesador ~0,7 s justo durante el fundido, y
 * el fundido se trababa al final. El ejemplo espera a
 * esto antes de dibujarse. «pagereveal» sale antes del primer cuadro y este archivo se carga antes, así que llega a
 * tiempo; en los navegadores que no lo tienen no hay fundido entre páginas y no se espera. */
const fundidoTerminado: Promise<void> =
  typeof window === "undefined" || !("onpagereveal" in window)
    ? Promise.resolve()
    : new Promise((listo) => {
        // el aviso lo escucha un renglón de app.html, que corre antes de la primera pintura; este archivo llega
        // después. Si ese renglón no está, se escucha acá como antes.
        const avisado = (window as Window & { __fsFundido?: Promise<void> }).__fsFundido;
        if (avisado) avisado.then(() => listo(), () => listo());
        else
          addEventListener(
            "pagereveal",
            (e) => {
              const vt = (e as Event & { viewTransition?: { finished: Promise<void> } | null }).viewTransition;
              if (vt) vt.finished.then(() => listo(), () => listo());
              else listo();
            },
            { once: true },
          );
        // por las dudas: el fundido dura 0,45 s, nunca se espera más que esto. Si la página se está armando por
        // adelantado, se cuenta desde que se muestra (si no, con el mouse apoyado unos segundos ya había vencido)
        if (armandoPorAdelantado()) document.addEventListener("prerenderingchange", () => setTimeout(listo, 1200), { once: true });
        else setTimeout(listo, 1200);
      });

export function finDelFundido(): Promise<void> {
  return fundidoTerminado;
}

export function reducirMovimiento(): boolean {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}
