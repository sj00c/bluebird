export const CAUSES: Record<string, string> = {
  T: "기술 미성숙",
  D: "데이터 부족",
  R: "규제",
  M: "시장·수요",
  C: "사업화 역량·자금",
  O: "기타",
  U: "판단 불가",
};

export const CHANGE_KINDS: Record<string, string> = {
  dataset_opened: "데이터 개방",
  law_effective: "법령 시행",
  announcement: "지원 공고",
  policy_news: "정책",
  tech: "기술",
};

export const VERDICTS: Record<string, string> = {
  now: "지금 가능",
  conditional: "조건부 가능",
};

export const OBJECTION_KINDS: Record<string, string> = {
  fact: "사실 오류",
  cause: "막힌 이유 이견",
  change: "바뀐 것 이견",
  privacy: "개인정보",
  other: "기타",
};

export const OBJECTION_STATUS: Record<string, string> = {
  open: "처리 대기",
  accepted: "수용",
  rejected: "기각",
};

export const ROUNDS: Record<string, string> = {
  final: "최종",
  expert: "전문가",
  audit: "감사",
  coder_a: "코더",
  coder_b: "코더",
};

export const DECISIONS: Record<string, string> = {
  approve: "승인",
  reject: "반려",
};

export const STAGES = ["s0", "s1", "s2", "s3", "s4", "s5", "s6"] as const;

export function cause(c: string | null | undefined): string {
  if (!c) return "-";
  return CAUSES[c] ? `${c} ${CAUSES[c]}` : c;
}

export function when(v: string | null | undefined): string {
  return v ? v.replace("T", " ").slice(0, 16) : "-";
}
