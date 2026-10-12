import type { Changes, Detail } from "@/lib/contracts";
import { CHANGE_KINDS } from "@/lib/labels";
import { EvidenceLink } from "./evidence-link";
import { MatchForm } from "./workflow-forms";
const verdictName: Record<string, string> = {
  yes: "연결됨",
  partial: "부분 연결",
  no: "연결 안 됨",
  human: "담당자 확인",
};

export function ChangeSection({
  detail: d,
  canAuthor,
  changeQuery,
  changes,
}: {
  detail: Detail;
  canAuthor: boolean;
  changeQuery: string;
  changes: Changes;
}) {
  const id = d.idea.id;
  return (
    <section className="card" id="changes">
      <h2>04 · 바뀐 조건 연결</h2>
      <ul className="instructions">
        <li>변화 연결 ≠ 공개 활용 가능</li>
        <li>서버 판정: 원인 적합성·출처 확인·검토 상태</li>
      </ul>
      {d.matches.length ? (
        d.matches.map((m) => (
          <article key={m.id} className="evidence">
            <div>
              <span className="tag">{CHANGE_KINDS[m.kind] ?? m.kind}</span>
              <span className={`tag ${m.eligible ? "positive" : ""}`}>
                {m.eligible ? "단계 근거로 사용 가능" : "조건 확인 필요"}
              </span>
            </div>
            <h3>
              {m.url ? (
                <EvidenceLink href={m.url}>{m.title}</EvidenceLink>
              ) : (
                m.title
              )}
            </h3>
            <p className="muted">
              {m.occurred_at ?? "일자 미상"} · 확인{" "}
              {m.verify_status ?? "미확인"} · 연결{" "}
              {verdictName[m.llm_verdict ?? ""] ?? m.llm_verdict ?? "미판정"} ·
              상태 {m.status ?? "미기록"}
            </p>
            <details>
              <summary>변화 내용·가능 조건</summary>
              <ul>
                {m.what_changed.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
              {m.how_now && (
                <p>
                  <b>지금은 </b>
                  {m.how_now}
                </p>
              )}
            </details>
          </article>
        ))
      ) : (
        <div className="pending">연결된 변화 없음</div>
      )}
      {canAuthor && (
        <>
          <h3>수집된 변화 찾기</h3>
          <p className="hint">검색·연결: 수집된 변화만 · 신규 수집: jobs</p>
          <form
            method="get"
            action={`/ideas/${encodeURIComponent(id)}#changes`}
            className="search-form"
          >
            <label htmlFor="change-search">
              변화 제목 또는 ID
              <input
                type="search"
                id="change-search"
                name="change_q"
                defaultValue={changeQuery}
                maxLength={200}
              />
            </label>
            <button type="submit">변화 검색</button>
          </form>
          <p className="hint">최대 50개 · 결과 없음: 검색어 구체화</p>
          <MatchForm detail={d} changes={changes.items} />
        </>
      )}
    </section>
  );
}
