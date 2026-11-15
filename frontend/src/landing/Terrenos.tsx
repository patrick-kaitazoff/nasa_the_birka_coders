import { useEffect, useRef, useState } from "react";
import puconEntrada from "./terrenos/pucon-entrada.mp4";
import puconVuelta from "./terrenos/pucon-vuelta.mp4";
import puconPoster from "./terrenos/pucon-poster.webp";
import moselaEntrada from "./terrenos/mosela-entrada.mp4";
import moselaVuelta from "./terrenos/mosela-vuelta.mp4";
import moselaPoster from "./terrenos/mosela-poster.webp";
import lunarejoEntrada from "./terrenos/lunarejo-entrada.mp4";
import lunarejoVuelta from "./terrenos/lunarejo-vuelta.mp4";
import lunarejoPoster from "./terrenos/lunarejo-poster.webp";

/** Tres terrenos de ejemplo en 3D, cada uno con su solución armada. «Ver solución» abre la herramienta con ese campo (/app?demo=<id>, scripts/armar_terrenos.py):
 * el plan, las alternativas de cada lote y el chat para preguntar.
 *
 * Los videos están renderizados en Blender con el relieve Copernicus GLO-30 y la foto de Esri. Cada uno tiene una
 * entrada (la cámara baja desde arriba, 3 s) que se ve una sola vez y una vuelta de 52 s que empalma consigo misma y
 * queda en loop: son dos <video> apilados, así el cambio no deja un cuadro en negro. Los archivos pesan menos de 4 MB
 * porque en Vercel los sirve la función de Python, que no devuelve respuestas de más de 4,5 MB. */
const TERRENOS = [
  {
    id: "pucon",
    titulo: "Campo entre un volcán y un lago",
    lugar: "Pucón, Araucanía · Chile",
    texto: "Lechería al pie del volcán Villarrica, con laderas de mucha pendiente y heladas.",
    entrada: puconEntrada,
    vuelta: puconVuelta,
    poster: puconPoster,
  },
  {
    id: "mosela",
    titulo: "Vega de un río entre viñedos",
    lugar: "Bremm, río Mosela · Alemania",
    texto: "Agricultura en la curva del río, con el suelo de la ladera que se lava.",
    entrada: moselaEntrada,
    vuelta: moselaVuelta,
    poster: moselaPoster,
  },
  {
    id: "lunarejo",
    titulo: "Campo al borde de las quebradas",
    lugar: "Valle del Lunarejo · Rivera, Uruguay",
    texto: "Ganadería en la meseta, con suelos poco profundos. Relieve exagerado tres veces para que se vea.",
    entrada: lunarejoEntrada,
    vuelta: lunarejoVuelta,
    poster: lunarejoPoster,
  },
];

type Terreno = (typeof TERRENOS)[number];

function TarjetaTerreno({ t, pausado, alPausar, alReanudar, adelantar }: { t: Terreno; pausado: boolean; alPausar: () => void; alReanudar: () => void; adelantar: boolean }) {
  const [visto, setVisto] = useState(false); // el video se baja recién cuando la tarjeta asoma
  const [enPantalla, setEnPantalla] = useState(false);
  const [enVuelta, setEnVuelta] = useState(false);
  const escenario = useRef<HTMLDivElement>(null);
  const vEntrada = useRef<HTMLVideoElement>(null);
  const vVuelta = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const el = escenario.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) setVisto(true);
        setEnPantalla(e.intersectionRatio >= 0.25);
      },
      { rootMargin: "300px 0px", threshold: [0, 0.25] },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // reproduce solo con la tarjeta en pantalla
  useEffect(() => {
    const a = vEntrada.current, b = vVuelta.current;
    if (!a || !b || !visto) return;
    const activo = enVuelta ? b : a;
    (enVuelta ? a : b).pause();
    if (enPantalla && !pausado)
      void activo.play().catch((e: unknown) => {
        // si el navegador no deja reproducir solo, queda en pausa con el botón
        if (e instanceof DOMException && e.name === "NotAllowedError") alPausar();
      });
    else activo.pause();
  }, [enVuelta, enPantalla, pausado, visto, alPausar]);

  return (
    <li className="lp-terreno">
      {/* Sin botón de pausa. Si los videos
          quedaron quietos (el sistema pide menos movimiento o el navegador no dejó arrancarlos), tocar uno los pone a andar */}
      <div className="lp-terreno-escenario" ref={escenario} onClick={pausado ? alReanudar : undefined}>
        <video ref={vEntrada} src={visto || adelantar ? t.entrada : undefined} poster={t.poster} muted playsInline
          preload={visto || adelantar ? "auto" : "none"} onEnded={() => setEnVuelta(true)} aria-hidden />
        <video ref={vVuelta} className={enVuelta ? "visible" : ""} src={visto ? t.vuelta : undefined} muted playsInline loop
          preload={visto ? "auto" : "none"} aria-hidden />
      </div>
      <div className="lp-terreno-texto">
        <p className="lp-terreno-lugar">{t.lugar}</p>
        <h3>{t.titulo}</h3>
        <p>{t.texto}</p>
      </div>
      <a className="lp-btn lp-terreno-btn" href={`/app?demo=${t.id}`}>Ver solución</a>
    </li>
  );
}

export function Terrenos() {
  const [pausado, setPausado] = useState(false);
  // sin movimiento automático para quien lo pidió en el sistema: arranca en pausa
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) setPausado(true);
  }, []);
  const pausar = useRef(() => setPausado(true)).current;
  const reanudar = useRef(() => setPausado(false)).current;
  // La entrada de cada video (250 KB) se baja sola cuando la portada ya cargó y quedó quieta, sin esperar a
  // que la tarjeta asome: al bajar, el terreno arranca enseguida en vez de quedarse un rato en la foto fija. La vuelta
  // larga (3 MB cada una) sigue bajándose recién cuando la tarjeta está por verse.
  const [adelantar, setAdelantar] = useState(false);
  useEffect(() => {
    if ((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData) return;
    let t = 0;
    const pedir = () => { t = window.setTimeout(() => setAdelantar(true), 2500); };
    if (document.readyState === "complete") pedir();
    else addEventListener("load", pedir, { once: true });
    return () => { clearTimeout(t); removeEventListener("load", pedir); };
  }, []);

  return (
    <div className="lp-terrenos">
      <ul className="lp-terrenos-grilla">
        {TERRENOS.map((t) => <TarjetaTerreno key={t.id} t={t} pausado={pausado} alPausar={pausar} alReanudar={reanudar} adelantar={adelantar} />)}
      </ul>
      <div className="lp-terrenos-pie">
        <p className="lp-terrenos-nota">
          Videos renderizados con el relieve Copernicus GLO-30 (30 m) y la imagen satelital de Esri. Las soluciones usan
          datos reales del lugar; los productores y sus respuestas son inventados.
        </p>
      </div>
    </div>
  );
}
