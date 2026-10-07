// 화면 공통 문구. 과거의 부재를 단정하는 표현은 쓰지 않는다(목록: pipeline/bluebird/wording.py FORBIDDEN).
export const CAUSE: Record<string, string> = {
  T: "기술 미성숙",
  D: "데이터 접근 제약",
  R: "제도·규제",
  M: "수요·시장 부재",
  C: "자원·역량·후속연계",
  O: "대체·중복",
  U: "판단 불가",
};

export const CHANGE_KIND: Record<string, string> = {
  dataset_opened: "데이터 개방",
  law_effective: "법령 시행",
  announcement: "지원 공고",
  policy_news: "정책",
  tech: "기술",
};

export const VERDICT: Record<string, string> = { now: "지금 가능", conditional: "조건부 가능", hold: "보류" };

// 데이터 개방 신호의 근거 수준(목록개방현황 스냅샷 비교). 날짜만으로 "새로 열렸다"고 말하지 않는다.
export function tierText(c: { kind: string; tier: string | null; occurred_at: string | null; registered_at: string | null }): string | null {
  if (c.kind !== "dataset_opened") return null;
  const reg = `포털 등록 ${c.registered_at ?? "-"}`;
  if (c.tier === "observed_new") return `파랑새 관측 신규 · ${reg}`;
  if (c.tier === "reappeared") return `목록에 다시 나타남 · ${reg}`;
  return reg;
}

// 사업화 흔적 확인 범위
export function traceText(status: string | null, externalSearch: string | null): string | null {
  if (!status || status === "pending") return null;
  return externalSearch === "done" ? "외부 검색(뉴스·특허) 실시" : "외부 검색 미실시";
}

export const VERDICT_PILL: Record<string, string> = { now: "hi", conditional: "mid", hold: "lo" };

// 시의성 네 축(core.timeliness tech·data·regulation·policy). 화면 시안의 이름을 쓴다.
export const AXES: { key: "tech" | "data" | "regulation" | "policy"; label: string }[] = [
  { key: "tech", label: "기술 준비도" },
  { key: "data", label: "데이터 개방도" },
  { key: "regulation", label: "제도 정합성" },
  { key: "policy", label: "정책 수요" },
];

// 사업화 흔적 판정(core.trace_verdict.status)
export const TRACE: Record<string, string> = {
  realized: "사업화됨",
  pivot: "방향 바꿔 사업화",
  similar_unlinked: "비슷한 사업 있음(연결 미확인)",
  award_only: "수상 기록만",
  none: "흔적 없음",
  pending: "확인 전",
};

// 사업화 흔적 확인 항목. 외부 검색(뉴스·특허)은 키가 있어야 실시된다(publish.idea.external_search).
export const TRACE_ITEMS: { label: string; via: string; external: boolean }[] = [
  { label: "후속 보도(뉴스·웹)", via: "네이버 뉴스 검색", external: true },
  { label: "특허·상표", via: "KIPRIS Plus", external: true },
  { label: "후속 지원사업 선정", via: "K-Startup·기업마당 공고", external: false },
];
