// 화면 공통 문구. 과거의 부재를 단정하는 표현은 쓰지 않는다(목록: pipeline/bluebird/wording.py FORBIDDEN).
export const CAUSE: Record<string, string> = {
  T: "기술 미성숙",
  D: "데이터 부족",
  R: "규제",
  M: "시장·수요",
  C: "사업화 역량·자금",
  O: "기타",
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
