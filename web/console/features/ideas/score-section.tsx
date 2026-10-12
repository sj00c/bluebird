import type { Detail } from "@/lib/contracts";
import { AXES, VERDICTS } from "@/lib/labels";
import { EvidenceLink } from "./evidence-link";
import { ScoreForm } from "./workflow-forms";

export function ScoreSection({
  detail: d,
  canAuthor,
}: {
  detail: Detail;
  canAuthor: boolean;
}) {
  const { timeliness } = d;
  return (
    <section className="card" id="score">
      <div className="section-heading">
        <h2>05 · 시의성 평가</h2>
        <span className="tag">
          {timeliness?.verdict
            ? (VERDICTS[timeliness.verdict] ?? timeliness.verdict)
            : "미평가"}
        </span>
      </div>
      {timeliness ? (
        <>
          <div className="score-summary">
            <strong>
              {timeliness.s ?? "—"}
              <small>시의성 S</small>
            </strong>
            <div>
              <b>{timeliness.n_scored ?? 0}개 축 평가</b>
              <p className="muted">
                기준일 {timeliness.as_of ?? "미기록"}
                <br />
                평가자 {timeliness.scored_by ?? "미기록"}
              </p>
            </div>
          </div>
          <div className="axis-grid">
            {Object.entries(AXES).map(([axis, label]) => {
              const key = axis as keyof typeof AXES;
              const url = timeliness.evidence?.[key];
              return (
                <div key={key}>
                  <small>{label}</small>
                  <b>
                    {timeliness[key] === null
                      ? "미평가"
                      : `${timeliness[key]} / 5`}
                  </b>
                  {url ? (
                    <EvidenceLink href={url}>근거 보기</EvidenceLink>
                  ) : (
                    <span className="muted">근거 미등록</span>
                  )}
                </div>
              );
            })}
          </div>
          {timeliness.resolve_condition && (
            <details>
              <summary>해결 조건 기록</summary>
              <div className="body">{timeliness.resolve_condition}</div>
            </details>
          )}
        </>
      ) : (
        <div className="pending">시의성 평가 미기록</div>
      )}
      {canAuthor && <ScoreForm detail={d} />}
    </section>
  );
}
