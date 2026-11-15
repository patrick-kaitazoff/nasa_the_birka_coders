import { etiquetaCortaTemporada } from "./eleccion";
import type { Analisis, Campo, Catalogo, Geo, Plan } from "../tipos";
import { colorCultivo, nombreCorto, nombreCultivo } from "../store";
import { proyectar, type Proyeccion } from "./PlanoSVG";
import { puntoInterior } from "../mapa/geo";
import { useIdioma } from "../i18n/idioma";
import { traducir } from "../i18n/traducir";

function fmt(n: number | null | undefined, d = 0, idioma: "es" | "en" = "es"): string {
  if (n == null || Number.isNaN(n)) return "—";
  const loc = idioma === "en" ? "en-US" : "es-UY";
  return n.toLocaleString(loc, { maximumFractionDigits: d, minimumFractionDigits: d });
}

function rectRedondeado(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const radio = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radio, y);
  ctx.lineTo(x + w - radio, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radio);
  ctx.lineTo(x + w, y + h - radio);
  ctx.quadraticCurveTo(x + w, y + h, x + w - radio, y + h);
  ctx.lineTo(x + radio, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - radio);
  ctx.lineTo(x, y + radio);
  ctx.quadraticCurveTo(x, y, x + radio, y);
  ctx.closePath();
}

function trazarGeometria(ctx: CanvasRenderingContext2D, g: Geo, p: Proyeccion, offX = 0, offY = 0) {
  const poligonos: number[][][][] = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  ctx.beginPath();
  for (const poli of poligonos) {
    for (const anillo of poli) {
      anillo.forEach(([lon, lat], i) => {
        const px = offX + p.x(lon);
        const py = offY + p.y(lat);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
    }
  }
}

function truncarTexto(ctx: CanvasRenderingContext2D, texto: string, maxAncho: number): string {
  if (ctx.measureText(texto).width <= maxAncho) return texto;
  let s = texto;
  while (s.length > 1 && ctx.measureText(s + "…").width > maxAncho) {
    s = s.slice(0, -1);
  }
  return s + "…";
}

/**
 * Envuelve una imagen JPEG de anchoPx × altoPx en un archivo PDF 1.4 de una sola página A4 horizontal.
 * Usa /Filter /DCTDecode nativo de PDF, sin librerías externas.
 */
export function envolverJpegEnPdf(
  jpegBytes: Uint8Array,
  anchoPx: number,
  altoPx: number,
  anchoPt = 841.89, // A4 horizontal: 297 mm
  altoPt = 595.28,  // A4 horizontal: 210 mm
): Uint8Array {
  const enc = new TextEncoder();
  const trozos: Uint8Array[] = [];
  let desplazamiento = 0;
  const offsets: number[] = [];

  function escribir(str: string) {
    const b = enc.encode(str);
    trozos.push(b);
    desplazamiento += b.length;
  }

  function escribirBytes(b: Uint8Array) {
    trozos.push(b);
    desplazamiento += b.length;
  }

  escribir("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");

  // Obj 1: Catalog
  offsets.push(desplazamiento);
  escribir("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");

  // Obj 2: Pages
  offsets.push(desplazamiento);
  escribir("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n");

  // Obj 3: Page
  offsets.push(desplazamiento);
  escribir(
    `3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${anchoPt.toFixed(2)} ${altoPt.toFixed(2)}] ` +
    `/Resources << /XObject << /Im1 4 0 R >> /ProcSet [/PDF /ImageC] >> ` +
    `/Contents 5 0 R >>\nendobj\n`
  );

  // Obj 4: Image XObject
  offsets.push(desplazamiento);
  escribir(
    `4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${anchoPx} /Height ${altoPx} ` +
    `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBytes.length} >>\nstream\n`
  );
  escribirBytes(jpegBytes);
  escribir("\nendstream\nendobj\n");

  // Obj 5: Contents
  offsets.push(desplazamiento);
  const contenido = `q\n${anchoPt.toFixed(2)} 0 0 ${altoPt.toFixed(2)} 0 0 cm\n/Im1 Do\nQ\n`;
  const contenidoBytes = enc.encode(contenido);
  escribir(`5 0 obj\n<< /Length ${contenidoBytes.length} >>\nstream\n${contenido}endstream\nendobj\n`);

  // Xref
  const startxref = desplazamiento;
  escribir("xref\n0 6\n0000000000 65535 f \n");
  for (const off of offsets) {
    escribir(String(off).padStart(10, "0") + " 00000 n \n");
  }
  escribir(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${startxref}\n%%EOF\n`);

  const total = trozos.reduce((acc, t) => acc + t.length, 0);
  const salida = new Uint8Array(total);
  let pos = 0;
  for (const t of trozos) {
    salida.set(t, pos);
    pos += t.length;
  }
  return salida;
}

/** Dibuja el plano completo en un canvas horizontal de alta resolución listo para A4 (2480 × 1754 px). */
export function dibujarPlanoCanvas(
  campo: Campo,
  plan: Plan,
  catalogo: Catalogo | null,
  analisis: Analisis | null,
): HTMLCanvasElement {
  const idioma = useIdioma.getState().idioma;
  const t = (s: string) => (idioma === "en" ? traducir(s) : s);

  const canvas = document.createElement("canvas");
  const W = 2480;
  const H = 1754;
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("No se pudo obtener el contexto 2D del canvas");

  // Fondo general
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, W, H);

  const margenX = 64;
  const anchoContenido = W - 2 * margenX;

  // 1. Encabezado
  const totalHa = campo.area_ha || campo.secciones.reduce((a, s) => a + (s.area_ha || 0), 0) || 0;
  const nombreCampo = campo.nombre || t("Campo");
  const fechaStr = new Date().toLocaleDateString(idioma === "en" ? "en-US" : "es-UY", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  // Marca "Seasons Ahead"
  rectRedondeado(ctx, margenX, 48, 140, 28, 6);
  ctx.fillStyle = "#eef7f2";
  ctx.fill();
  ctx.fillStyle = "#1b4332";
  ctx.font = "bold 13px Inter, system-ui, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText("SEASONS AHEAD", margenX + 14, 62);

  // Título principal
  ctx.fillStyle = "#12352a";
  ctx.font = "bold 34px Inter, system-ui, sans-serif";
  ctx.fillText(t("Plan de rotaciones"), margenX, 112);

  // Subtítulo con nombre, superficie y fecha
  ctx.fillStyle = "#4b5563";
  ctx.font = "500 20px Inter, system-ui, sans-serif";
  ctx.fillText(`${nombreCampo} · ${fmt(totalHa, 1, idioma)} ha · ${fechaStr}`, margenX, 145);

  // Tarjeta de erosión promedio en el encabezado
  const cardW = 620;
  const cardH = 92;
  const cardX = W - margenX - cardW;
  const cardY = 52;
  rectRedondeado(ctx, cardX, cardY, cardW, cardH, 12);
  ctx.fillStyle = "#f6faf8";
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = "#cce3d7";
  ctx.stroke();

  ctx.fillStyle = "#2d4a3e";
  ctx.font = "600 14px Inter, system-ui, sans-serif";
  ctx.fillText(t("Erosión media estimada:"), cardX + 18, cardY + 28);

  // Número con fuente grande y medición previa para que no solape la unidad
  ctx.fillStyle = "#12352a";
  ctx.font = "bold 28px Inter, system-ui, sans-serif";
  const txtVal = fmt(plan.erosion_media_plan, 1, idioma);
  const anchoVal = ctx.measureText(txtVal).width;
  ctx.fillText(txtVal, cardX + 18, cardY + 65);

  ctx.font = "500 15px Inter, system-ui, sans-serif";
  ctx.fillStyle = "#4b5563";
  ctx.fillText("t/ha/año", cardX + 26 + anchoVal, cardY + 65);

  // Diferencia porcentual con la erosión actual
  if (plan.erosion_media_actual > 0) {
    const diffPct = Math.round(100 * (1 - plan.erosion_media_plan / plan.erosion_media_actual));
    const mejora = plan.erosion_media_plan <= plan.erosion_media_actual;
    const diffTexto = `${mejora ? "−" : "+"}${Math.abs(diffPct)} %`;

    rectRedondeado(ctx, cardX + cardW - 220, cardY + 18, 202, 56, 8);
    ctx.fillStyle = mejora ? "#e8f5e9" : "#fff3e0";
    ctx.fill();

    ctx.fillStyle = mejora ? "#2e7d32" : "#c62828";
    ctx.font = "bold 20px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(diffTexto, cardX + cardW - 119, cardY + 42);

    ctx.fillStyle = "#556b60";
    ctx.font = "500 12px Inter, system-ui, sans-serif";
    ctx.fillText(`${t("hoy:")} ${fmt(plan.erosion_media_actual, 1, idioma)} t/ha/año`, cardX + cardW - 119, cardY + 62);
    ctx.textAlign = "left";
  }

  // Línea divisoria
  ctx.beginPath();
  ctx.moveTo(margenX, 172);
  ctx.lineTo(W - margenX, 172);
  ctx.lineWidth = 1;
  ctx.strokeStyle = "#e5e7eb";
  ctx.stroke();

  // 2. Mapas de las temporadas
  const ySeccionMapas = 196;
  ctx.fillStyle = "#2d4a3e";
  ctx.font = "bold 16px Inter, system-ui, sans-serif";
  ctx.fillText(t("PLANO POR TEMPORADA"), margenX, ySeccionMapas);

  const temporadas = plan.temporadas;
  const numTemp = temporadas.length;
  const separacion = 18;

  // Si son 4 temporadas o menos, van en 1 sola fila; si son más, en 2 filas con altura generosa
  const enDosFilas = numTemp > 4;
  const cols = enDosFilas ? Math.ceil(numTemp / 2) : numTemp;
  const anchoCaja = (anchoContenido - (cols - 1) * separacion) / cols;
  const altoCaja = enDosFilas ? 350 : 540;
  const yInicioCajas = ySeccionMapas + 14;

  const cultivoDeTemporada = (idx: number) => (sid: string) =>
    plan.secciones.find((a) => a.seccion_id === sid)?.cultivos[idx];

  temporadas.forEach((temp, i) => {
    const colIdx = enDosFilas ? i % cols : i;
    const filaIdx = enDosFilas ? Math.floor(i / cols) : 0;
    const boxX = margenX + colIdx * (anchoCaja + separacion);
    const boxY = yInicioCajas + filaIdx * (altoCaja + separacion);

    // Caja contenedora
    rectRedondeado(ctx, boxX, boxY, anchoCaja, altoCaja, 10);
    ctx.fillStyle = "#fcfdfc";
    ctx.fill();
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = "#d6ded9";
    ctx.stroke();

    // Encabezado de la caja de temporada
    const altoHeaderCaja = 38;
    ctx.save();
    ctx.beginPath();
    rectRedondeado(ctx, boxX, boxY, anchoCaja, altoHeaderCaja, 10);
    ctx.fillStyle = temp.tipo === "verano" ? "#fffbf0" : "#f0f7ff";
    ctx.fill();
    ctx.restore();

    // Pastilla de temporada
    const esVerano = temp.tipo === "verano";
    const pastillaW = anchoCaja < 400 ? 66 : 80;
    rectRedondeado(ctx, boxX + 10, boxY + 7, pastillaW, 24, 6);
    ctx.fillStyle = esVerano ? "#fef3c7" : "#dbeafe";
    ctx.fill();
    ctx.fillStyle = esVerano ? "#92400e" : "#1e40af";
    ctx.font = "bold 11.5px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(esVerano ? "Verano" : "Invierno", boxX + 10 + pastillaW / 2, boxY + 19);

    // Etiqueta completa de la temporada
    ctx.textAlign = "left";
    ctx.fillStyle = "#1f2937";
    ctx.font = "bold 14px Inter, system-ui, sans-serif";
    ctx.fillText(temp.etiqueta, boxX + 18 + pastillaW, boxY + 20);

    // Resumen de cobertura si hay espacio
    const resTemp = plan.resumen_temporadas[i];
    if (resTemp && anchoCaja >= 360) {
      ctx.textAlign = "right";
      ctx.fillStyle = "#4b5563";
      ctx.font = "500 12.5px Inter, system-ui, sans-serif";
      ctx.fillText(`${resTemp.pct_cubierto}% cubierto`, boxX + anchoCaja - 14, boxY + 20);
      ctx.textAlign = "left";
    }

    // Dibujo del mapa dentro de la caja
    if (campo.contorno) {
      const margenMapa = 16;
      const mapX = boxX + margenMapa;
      const mapY = boxY + altoHeaderCaja + margenMapa / 2;
      const mapW = anchoCaja - 2 * margenMapa;
      const mapH = altoCaja - altoHeaderCaja - margenMapa * 1.5;

      const p = proyectar(campo.contorno, mapW, mapH, enDosFilas ? 18 : 26);
      const getCultivo = cultivoDeTemporada(i);

      ctx.save();
      // Recortar al área del mapa
      ctx.beginPath();
      ctx.rect(mapX, mapY, mapW, mapH);
      ctx.clip();

      // Dibujar secciones
      for (const s of campo.secciones) {
        const cod = getCultivo(s.id);
        const col = cod ? colorCultivo(catalogo, cod) : "#e2e8f0";

        trazarGeometria(ctx, s.geometria, p, mapX, mapY);
        ctx.fillStyle = col;
        ctx.fill("evenodd");
        ctx.lineWidth = 1.6;
        ctx.strokeStyle = "#ffffff";
        ctx.stroke();

        // Rótulo interior solo si el mapa es grande (4 temporadas o menos)
        if (!enDosFilas) {
          try {
            const [lat, lon] = puntoInterior(s.geometria);
            const cx = mapX + p.x(lon);
            const cy = mapY + p.y(lat);
            const nombreSec = s.nombre;
            const nombreCult = cod ? nombreCorto(cod) : "";

            ctx.font = "bold 11px Inter, system-ui, sans-serif";
            const w1 = ctx.measureText(nombreSec).width;
            ctx.font = "500 10.5px Inter, system-ui, sans-serif";
            const w2 = ctx.measureText(nombreCult).width;
            const badgeW = Math.max(w1, w2) + 16;
            const badgeH = 32;

            rectRedondeado(ctx, cx - badgeW / 2, cy - badgeH / 2, badgeW, badgeH, 5);
            ctx.fillStyle = "rgba(255, 255, 255, 0.94)";
            ctx.fill();
            ctx.lineWidth = 1;
            ctx.strokeStyle = "rgba(0, 0, 0, 0.12)";
            ctx.stroke();

            ctx.textAlign = "center";
            ctx.fillStyle = "#111827";
            ctx.font = "bold 11px Inter, system-ui, sans-serif";
            ctx.fillText(nombreSec, cx, cy - 3);

            ctx.fillStyle = "#4b5563";
            ctx.font = "500 10.5px Inter, system-ui, sans-serif";
            ctx.fillText(nombreCult, cx, cy + 10);
            ctx.textAlign = "left";
          } catch {
            // si falla el punto interior, seguimos
          }
        }
      }

      // Contorno general del campo
      trazarGeometria(ctx, campo.contorno, p, mapX, mapY);
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = "#12352a";
      ctx.stroke();

      // En el primer mapa, dibujar rosa del norte y escala gráfica
      if (i === 0) {
        // Flecha del Norte
        const nX = mapX + mapW - 20;
        const nY = mapY + 28;
        ctx.beginPath();
        ctx.moveTo(nX, nY - 16);
        ctx.lineTo(nX + 6, nY + 4);
        ctx.lineTo(nX, nY);
        ctx.lineTo(nX - 6, nY + 4);
        ctx.closePath();
        ctx.fillStyle = "#12352a";
        ctx.fill();
        ctx.font = "bold 11px Inter, system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("N", nX, nY + 16);
        ctx.textAlign = "left";

        // Escala gráfica
        const metrosRef = p.metrosPorUnidad * mapW * 0.22;
        const pasosEscala = [50, 100, 200, 250, 500, 1000, 2000, 5000];
        const largoM = pasosEscala.reduce((a, b) => (Math.abs(b - metrosRef) < Math.abs(a - metrosRef) ? b : a));
        const largoPx = largoM / p.metrosPorUnidad;
        const scX = mapX + 14;
        const scY = mapY + mapH - 14;

        ctx.fillStyle = "#12352a";
        ctx.fillRect(scX, scY, largoPx, 4);
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(scX, scY, largoPx / 2, 4);
        ctx.lineWidth = 0.8;
        ctx.strokeStyle = "#12352a";
        ctx.strokeRect(scX, scY, largoPx / 2, 4);

        ctx.fillStyle = "#12352a";
        ctx.font = "600 10.5px Inter, system-ui, sans-serif";
        ctx.fillText(largoM >= 1000 ? `${largoM / 1000} km` : `${largoM} m`, scX, scY - 4);
      }

      ctx.restore();
    }
  });

  // 3. Leyenda de cultivos
  const yMapasFin = yInicioCajas + (enDosFilas ? 2 * altoCaja + separacion : altoCaja);
  const yLeyenda = yMapasFin + 20;

  ctx.fillStyle = "#2d4a3e";
  ctx.font = "bold 15px Inter, system-ui, sans-serif";
  ctx.fillText(t("CULTIVOS EN EL PLAN:"), margenX, yLeyenda + 12);

  const cultivosPlan = Array.from(new Set(plan.secciones.flatMap((a) => a.cultivos)));
  let curX = margenX + ctx.measureText(t("CULTIVOS EN EL PLAN:")).width + 24;
  let curY = yLeyenda + 12;

  cultivosPlan.forEach((cod) => {
    const col = colorCultivo(catalogo, cod);
    const nom = nombreCultivo(catalogo, cod, true);

    // Muestra de color
    rectRedondeado(ctx, curX, curY - 11, 24, 16, 4);
    ctx.fillStyle = col;
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(0, 0, 0, 0.15)";
    ctx.stroke();

    // Nombre del cultivo
    ctx.fillStyle = "#1f2937";
    ctx.font = "500 14px Inter, system-ui, sans-serif";
    ctx.fillText(nom, curX + 32, curY + 2);

    curX += 32 + ctx.measureText(nom).width + 28;
  });

  // 4. Tabla de rotación y erosión por sección
  const yTablaTitulo = yLeyenda + 40;
  ctx.fillStyle = "#2d4a3e";
  ctx.font = "bold 16px Inter, system-ui, sans-serif";
  ctx.fillText(t("RESUMEN DE ROTACIÓN Y EROSIÓN POR SECCIÓN"), margenX, yTablaTitulo);

  const yTabla = yTablaTitulo + 16;
  const altoFila = 42;

  // Anchos de columnas
  const wSec = 340;
  const wSup = 140;
  const wEroActual = 190;
  const wEroPlan = 190;
  const wTol = 170;
  const wEstado = 170;
  const wFijas = wSec + wSup + wEroActual + wEroPlan + wTol + wEstado;
  const wTemp = (anchoContenido - wFijas) / numTemp;

  // Cabecera de la tabla
  rectRedondeado(ctx, margenX, yTabla, anchoContenido, altoFila, 8);
  ctx.fillStyle = "#eef4f0";
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = "#d4ded7";
  ctx.stroke();

  ctx.fillStyle = "#12352a";
  ctx.font = "bold 13.5px Inter, system-ui, sans-serif";
  ctx.textBaseline = "middle";

  let colX = margenX + 16;
  ctx.fillText(t("Sección"), colX, yTabla + altoFila / 2);

  colX = margenX + wSec;
  ctx.fillText(t("Superficie"), colX, yTabla + altoFila / 2);

  temporadas.forEach((temp, i) => {
    const cx = margenX + wSec + wSup + i * wTemp + wTemp / 2;
    ctx.textAlign = "center";
    const etiquetaTemp = etiquetaCortaTemporada(temp);
    ctx.fillText(etiquetaTemp, cx, yTabla + altoFila / 2);
  });
  ctx.textAlign = "left";

  const xEroActual = margenX + wSec + wSup + numTemp * wTemp;
  ctx.fillText(t("Erosión actual"), xEroActual + 12, yTabla + altoFila / 2);

  const xEroPlan = xEroActual + wEroActual;
  ctx.fillText(t("Con el plan"), xEroPlan + 12, yTabla + altoFila / 2);

  const xTol = xEroPlan + wEroPlan;
  ctx.fillText(t("Tolerancia (T)"), xTol + 12, yTabla + altoFila / 2);

  const xEstado = xTol + wTol;
  ctx.fillText(t("Estado"), xEstado + 12, yTabla + altoFila / 2);

  // Filas por sección
  plan.secciones.forEach((secPlan, rowIdx) => {
    const rowY = yTabla + altoFila + rowIdx * altoFila;
    const esPar = rowIdx % 2 === 0;

    ctx.fillStyle = esPar ? "#ffffff" : "#fbfdfc";
    ctx.fillRect(margenX, rowY, anchoContenido, altoFila);

    ctx.beginPath();
    ctx.moveTo(margenX, rowY + altoFila);
    ctx.lineTo(margenX + anchoContenido, rowY + altoFila);
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#e5e7eb";
    ctx.stroke();

    // Datos agronómicos de la sección
    const secAn = analisis?.secciones.find((s) => s.id === secPlan.seccion_id);
    const opciones = secAn ? [secAn.actual, ...secAn.alternativas].filter(Boolean) : [];
    const evElegida = opciones.find((e) => e && e.id === secPlan.rotacion_id) || opciones[0];

    const eroActualVal = secAn?.actual?.erosion?.a_t_ha;
    const eroPlanVal = evElegida?.erosion?.a_t_ha;
    const tolVal = secAn?.suelo?.tolerancia_t ?? evElegida?.erosion?.tolerancia_t;
    const cumple = eroPlanVal != null && tolVal != null ? eroPlanVal <= tolVal : true;

    // Col 1: Nombre de la sección
    ctx.fillStyle = "#111827";
    ctx.font = "600 14px Inter, system-ui, sans-serif";
    ctx.fillText(truncarTexto(ctx, secPlan.seccion, wSec - 32), margenX + 16, rowY + altoFila / 2);

    // Col 2: Superficie
    ctx.fillStyle = "#4b5563";
    ctx.font = "500 13.5px Inter, system-ui, sans-serif";
    ctx.fillText(`${fmt(secPlan.area_ha, 1, idioma)} ha`, margenX + wSec, rowY + altoFila / 2);

    // Cols de temporadas: Cultivo con pastilla de color
    temporadas.forEach((_, tempIdx) => {
      const cod = secPlan.cultivos[tempIdx];
      const cx = margenX + wSec + wSup + tempIdx * wTemp + wTemp / 2;
      const nomCorto = cod ? nombreCorto(cod) : "—";
      const col = cod ? colorCultivo(catalogo, cod) : "#e2e8f0";

      ctx.font = "bold 12px Inter, system-ui, sans-serif";
      const textW = ctx.measureText(nomCorto).width;
      const pillW = Math.min(wTemp - 12, textW + 18);
      const pillH = 26;

      rectRedondeado(ctx, cx - pillW / 2, rowY + (altoFila - pillH) / 2, pillW, pillH, 5);
      ctx.fillStyle = col;
      ctx.fill();

      ctx.fillStyle = "#ffffff";
      ctx.textAlign = "center";
      ctx.fillText(nomCorto, cx, rowY + altoFila / 2);
    });
    ctx.textAlign = "left";

    // Col Erosión actual
    ctx.fillStyle = "#4b5563";
    ctx.font = "500 13.5px Inter, system-ui, sans-serif";
    ctx.fillText(
      eroActualVal != null ? `${fmt(eroActualVal, 1, idioma)} t/ha/año` : "—",
      xEroActual + 12,
      rowY + altoFila / 2,
    );

    // Col Con el plan
    ctx.fillStyle = "#12352a";
    ctx.font = "bold 14px Inter, system-ui, sans-serif";
    ctx.fillText(
      eroPlanVal != null ? `${fmt(eroPlanVal, 1, idioma)} t/ha/año` : "—",
      xEroPlan + 12,
      rowY + altoFila / 2,
    );

    // Col Tolerancia (T)
    ctx.fillStyle = "#4b5563";
    ctx.font = "500 13.5px Inter, system-ui, sans-serif";
    ctx.fillText(tolVal != null ? `${fmt(tolVal, 1, idioma)} t/ha/año` : "—", xTol + 12, rowY + altoFila / 2);

    // Col Estado (Cumple / Excede)
    const estadoPillW = 108;
    const estadoPillH = 26;
    rectRedondeado(ctx, xEstado + 12, rowY + (altoFila - estadoPillH) / 2, estadoPillW, estadoPillH, 6);
    ctx.fillStyle = cumple ? "#e8f5e9" : "#fff3e0";
    ctx.fill();

    ctx.textAlign = "center";
    ctx.fillStyle = cumple ? "#2e7d32" : "#c62828";
    ctx.font = "bold 12px Inter, system-ui, sans-serif";
    ctx.fillText(cumple ? `✓ ${t("Cumple")}` : `⚠ ${t("Excede")}`, xEstado + 12 + estadoPillW / 2, rowY + altoFila / 2);
    ctx.textAlign = "left";
  });

  // Fila de resumen total / promedio
  const yFilaTotal = yTabla + altoFila + plan.secciones.length * altoFila;
  rectRedondeado(ctx, margenX, yFilaTotal, anchoContenido, altoFila, 6);
  ctx.fillStyle = "#f3f7f4";
  ctx.fill();
  ctx.lineWidth = 1.4;
  ctx.strokeStyle = "#c8d9ce";
  ctx.stroke();

  ctx.fillStyle = "#12352a";
  ctx.font = "bold 14px Inter, system-ui, sans-serif";
  ctx.fillText(t("Total / Promedio"), margenX + 16, yFilaTotal + altoFila / 2);
  ctx.fillText(`${fmt(totalHa, 1, idioma)} ha`, margenX + wSec, yFilaTotal + altoFila / 2);

  ctx.fillStyle = "#4b5563";
  ctx.font = "600 13.5px Inter, system-ui, sans-serif";
  ctx.fillText(`${fmt(plan.erosion_media_actual, 1, idioma)} t/ha/año`, xEroActual + 12, yFilaTotal + altoFila / 2);

  ctx.fillStyle = "#12352a";
  ctx.font = "bold 14px Inter, system-ui, sans-serif";
  ctx.fillText(`${fmt(plan.erosion_media_plan, 1, idioma)} t/ha/año`, xEroPlan + 12, yFilaTotal + altoFila / 2);

  ctx.fillStyle = "#6b7280";
  ctx.fillText("—", xTol + 12, yFilaTotal + altoFila / 2);

  if (plan.erosion_media_actual > 0) {
    const mejora = plan.erosion_media_plan <= plan.erosion_media_actual;
    const diffPct = Math.round(100 * (1 - plan.erosion_media_plan / plan.erosion_media_actual));
    ctx.fillStyle = mejora ? "#2e7d32" : "#c62828";
    ctx.font = "bold 12.5px Inter, system-ui, sans-serif";
    ctx.fillText(
      mejora ? `Baja ${diffPct} %` : `Sube ${Math.abs(diffPct)} %`,
      xEstado + 12,
      yFilaTotal + altoFila / 2,
    );
  }

  // 5. Pie de página
  const yPie = H - 36;
  ctx.fillStyle = "#6b7280";
  ctx.font = "500 13px Inter, system-ui, sans-serif";
  ctx.fillText(
    t("Generado con Seasons Ahead · Datos: GPM IMERG (lluvia), NASA POWER (clima), MODIS (cobertura), MGAP (suelos)"),
    margenX,
    yPie,
  );

  ctx.textAlign = "right";
  ctx.font = "italic 13px Inter, system-ui, sans-serif";
  ctx.fillText(t("Documento de planificación agronómica · Revisar con su ingeniero agrónomo"), W - margenX, yPie);
  ctx.textAlign = "left";

  return canvas;
}

/** Descarga el plano del campo con rotaciones y erosión en PDF estándar A4 horizontal (o PNG si falla). */
export async function descargarPlano(
  campo: Campo,
  plan: Plan,
  catalogo: Catalogo | null,
  analisis: Analisis | null,
): Promise<void> {
  const canvas = dibujarPlanoCanvas(campo, plan, catalogo, analisis);

  const nombreLimpio = (campo.nombre || "campo")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const fechaIso = new Date().toISOString().slice(0, 10);

  // Intentar generar PDF A4 horizontal con /Filter /DCTDecode
  try {
    const jpegBlob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!jpegBlob) throw new Error("No se pudo exportar la imagen JPEG del canvas");

    const jpegBuffer = await jpegBlob.arrayBuffer();
    const pdfBytes = envolverJpegEnPdf(new Uint8Array(jpegBuffer), canvas.width, canvas.height);
    const pdfBlob = new Blob([pdfBytes], { type: "application/pdf" });

    const url = URL.createObjectURL(pdfBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `plan-rotaciones-${nombreLimpio}-${fechaIso}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    return;
  } catch (err) {
    console.error("Fallo la generación del PDF, descargando como PNG de respaldo:", err);
  }

  // Respaldo en imagen PNG de alta resolución
  const pngBlob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (pngBlob) {
    const url = URL.createObjectURL(pngBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `plan-rotaciones-${nombreLimpio}-${fechaIso}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
}
