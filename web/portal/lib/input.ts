export const PAGE_SIZE = 50;

export const MAX_PAGE = 100_000;

export function parsePage(raw: unknown): number {
  const value =
    typeof raw === "number"
      ? raw
      : typeof raw === "string" && /^\d+$/.test(raw)
        ? Number(raw)
        : NaN;
  return Number.isSafeInteger(value) && value > 0
    ? Math.min(value, MAX_PAGE)
    : 1;
}
// 검색어: 제어문자(NUL 등)를 지우고 공백을 정리한 뒤 200자까지. Postgres text에는 NUL이 들어갈 수 없다.
export function cleanQuery(raw: unknown): string {
  // eslint-disable-next-line no-control-regex
  return (typeof raw === "string" ? raw : "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 200);
}
export const OBJECTION_KINDS = [
  "fact",
  "cause",
  "change",
  "privacy",
  "other",
] as const;
