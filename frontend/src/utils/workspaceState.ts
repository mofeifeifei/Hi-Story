export function readNumberList(key: string): number[] | null {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return Array.isArray(value) ? value.map(Number).filter(Number.isFinite) : null;
  } catch {
    return null;
  }
}

export function writeNumberList(key: string, value: number[]): void {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage may be disabled. */ }
}

export function readScroll(key: string): number {
  try { return Math.max(0, Number(localStorage.getItem(key) || 0)); } catch { return 0; }
}

export function writeScroll(key: string, value: number): void {
  try { localStorage.setItem(key, String(Math.max(0, value))); } catch { /* Storage may be disabled. */ }
}
