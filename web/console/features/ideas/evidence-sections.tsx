import type { Detail } from "@/lib/contracts";
import { cause, TRACE_STATUS } from "@/lib/labels";
import { EvidenceLink } from "./evidence-link";
import { DiagnosisForm, TraceForm } from "./workflow-forms";

export function EvidenceSections({
  detail: d,
  canAuthor,
}: {
  detail: Detail;
  canAuthor: boolean;
}) {
  const { idea, card, trace, diagnosis } = d;
  return (
    <>
      <section className="card" id="original">
        <div className="section-heading">
          <h2>01 · 원본과 구조화 카드</h2>
          <span className="tag">{idea.source_id}</span>
        </div>
        <ul className="instructions">
          <li>원본 공개 정책: {idea.public_ok ? "허용" : "비공개"}</li>
          <li>개별 분석 공개: 별도 검토·승인 필요</li>
          {idea.source_url && (
            <li>
              <EvidenceLink href={idea.source_url}>공식 원문</EvidenceLink>
            </li>
          )}
        </ul>
        <details>
          <summary>원본 본문 확인</summary>
          {idea.body ? (
            <div className="body">{idea.body}</div>
          ) : (
            <div className="pending">원본 본문 없음</div>
          )}
        </details>
        {card ? (
          <details>
            <summary>구조화 카드 · 문제·해법·데이터</summary>
            <h3>풀려던 문제</h3>
            <div className="body">{card.problem ?? "추출 내용 없음"}</div>
            <h3>제안한 해법</h3>
            <div className="body">{card.solution ?? "추출 내용 없음"}</div>
            <h3>필요했던 데이터</h3>
            {card.missing_data.length ? (
              card.missing_data.map((m, i) => (
                <div className="evidence" key={i}>
                  <b>{m.name}</b>
                  {m.excerpt && <p>{m.excerpt}</p>}
                </div>
              ))
            ) : (
              <p className="muted">데이터 요구사항 미기록</p>
            )}
            <p className="provenance">
              카드 종류 {card.card_kind ?? "미분류"} · 추출{" "}
              {card.extractor ?? "미기록"}
            </p>
          </details>
        ) : (
          <div className="pending">
            카드 미생성 · 수집 원본만으로 분석·승인을 판단하지 않음
          </div>
        )}
      </section>
      <section className="card" id="trace">
        <div className="section-heading">
          <h2>02 · 실현 흔적 확인</h2>
          <span className="tag">
            {trace?.status
              ? (TRACE_STATUS[trace.status] ?? trace.status)
              : "미판정"}
          </span>
        </div>
        {trace ? (
          <>
            <ul className="instructions">
              <li>실현·방향 전환·유사 사례: 재조명 대상 제외 가능</li>
              <li>자동 검색 결과: 검토 후보</li>
            </ul>
            {trace.checks.length ? (
              <ul className="evidence-list">
                {trace.checks.map((check, i) => (
                  <li key={i}>
                    <b>{check.item === "manual" ? "사람 확인" : check.item}</b>
                    <span className="tag">
                      {check.result === "found"
                        ? "흔적 있음"
                        : check.result === "none"
                          ? "흔적 없음"
                          : check.result}
                    </span>
                    <details>
                      <summary>확인 근거·메모</summary>
                      {check.detail &&
                        Object.entries(check.detail)
                          .filter(([, v]) => v !== null && v !== "")
                          .map(([key, value]) => (
                            <p className="muted" key={key}>
                              <b>
                                {(
                                  {
                                    note: "메모",
                                    by: "확인자",
                                    status: "판정",
                                    url: "근거",
                                  } as Record<string, string>
                                )[key] ?? key}
                                :{" "}
                              </b>
                              {key === "url" && typeof value === "string" ? (
                                <EvidenceLink href={value}>
                                  {value}
                                </EvidenceLink>
                              ) : typeof value === "string" ? (
                                (TRACE_STATUS[value] ?? value)
                              ) : (
                                JSON.stringify(value)
                              )}
                            </p>
                          ))}
                    </details>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="pending">세부 확인 기록 없음</div>
            )}
            <p className="provenance">
              확인 프로파일 {trace.profile_version ?? "미기록"}
            </p>
          </>
        ) : (
          <div className="pending">흔적 판정 미기록</div>
        )}
        {canAuthor && <TraceForm detail={d} />}
      </section>
      <section className="card" id="diagnosis">
        <h2>03 · 막힌 이유와 근거</h2>
        {diagnosis ? (
          <>
            <p>
              <span className="tag">{cause(diagnosis.cause)}</span>
              {diagnosis.secondary && (
                <span className="tag">보조 {cause(diagnosis.secondary)}</span>
              )}
            </p>
            <details>
              <summary>진단 이유·근거 {diagnosis.evidence.length}건</summary>
              <div className="body">
                {diagnosis.rationale ?? "진단 사유 미기록"}
              </div>
              <ul className="evidence-list">
                {diagnosis.evidence.map((e, i) => (
                  <li key={i}>
                    <EvidenceLink href={e.url}>{e.url}</EvidenceLink>
                    {e.excerpt && <blockquote>{e.excerpt}</blockquote>}
                  </li>
                ))}
              </ul>
              {!diagnosis.evidence.length && (
                <p className="hint">진단 근거 없음</p>
              )}
            </details>
            <p className="provenance">
              진단 {diagnosis.decided_by ?? "미기록"} · 추출{" "}
              {diagnosis.extractor ?? "미기록"}
            </p>
          </>
        ) : (
          <div className="pending">원인 진단 미작성</div>
        )}
        {canAuthor && <DiagnosisForm detail={d} />}
      </section>
    </>
  );
}
