/** Intervalo de Wilson (80 %) para «x de cada 10 años»: la misma cuenta que analisis/incertidumbre.py del
 * backend. Con ~35 años, «3 de cada 10» puede ser en verdad entre 2 y 4. */
export function wilson(p: number | null | undefined, n: number | null | undefined, z = 1.2816): [number, number] | null {
  if (p == null || !n) return null;
  const den = 1 + (z * z) / n;
  const centro = (p + (z * z) / (2 * n)) / den;
  const medio = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / den;
  return [Math.max(0, centro - medio), Math.min(1, centro + medio)];
}
