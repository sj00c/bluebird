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
  hold: "보류",
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
export const QUEUE_STAGES = ["raw", ...STAGES] as const;

export const STAGE_NAMES: Record<string, string> = {
  raw: "수집 원본",
  s0: "카드 준비",
  s1: "흔적 확인",
  s2: "원인 진단",
  s3: "변화 연결",
  s4: "시의성 평가",
  s5: "최종 승인",
  s6: "공개 반영",
};
export const TRACE_STATUS: Record<string, string> = {
  realized: "실현·사업화 확인",
  pivot: "방향 전환",
  similar_unlinked: "유사 사례 (연결 미확인)",
  award_only: "수상 기록만 확인",
  none: "실현 흔적 없음",
  pending: "판정 대기",
};
export const ROLES: Record<string, string> = {
  reviewer: "검토자",
  expert: "전문가",
  auditor: "감사자",
  coder: "독립 코더",
};
export const AXES = {
  tech: "기술",
  data: "데이터",
  regulation: "규제",
  policy: "정책",
} as const;

export function cause(c: string | null | undefined): string {
  if (!c) return "-";
  return CAUSES[c] ? `${c} ${CAUSES[c]}` : c;
}

export function when(v: string | null | undefined): string {
  return v ? v.replace("T", " ").slice(0, 16) : "-";
}
