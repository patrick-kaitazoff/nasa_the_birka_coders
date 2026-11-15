import type { Analisis } from "../tipos";

/** De dónde salió la lluvia del análisis: "GPM IMERG" desde 2000, o "NASA POWER" si IMERG no contestó o el
 * análisis es de antes de ese cambio. */
export function fuenteLluvia(analisis: Analisis | null | undefined): "GPM IMERG" | "NASA POWER" {
  return analisis?.clima?.fuente_lluvia === "GPM IMERG" ? "GPM IMERG" : "NASA POWER";
}
