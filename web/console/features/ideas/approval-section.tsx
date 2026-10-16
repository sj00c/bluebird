import type { Detail, Me } from "@/lib/contracts";
import { when } from "@/lib/labels";
import { ReviewForm } from "./workflow-forms";

export function ApprovalSection({ detail: d, me }: { detail: Detail; me: Me }) {
  const { idea } = d;
  const id = idea.id;
  return (
    <section className="card" id="approval">
      <h2>06 · 검토와 승인</h2>
      <ul className="instructions">
        <li>역할별 허용 작업만 표시</li>
        <li>전문가·감사 승인 ≠ 최종 공개 승인</li>
      </ul>
      {idea.withheld_at ? (
        <div className="msg err">
          원본 공개 중단 · {when(idea.withheld_at)}
          <br />
          승인 불가: 원본 공개 중단 상태
        </div>
      ) : (
        <>
          {me.roles.includes("reviewer") && (
            <>
              <h3>최종 검토</h3>
              {d.stage.s4 ? (
                <ReviewForm
                  id={id}
                  round="final"
                  decision="approve"
                  label={d.stage.s5 ? "최종 승인 다시 기록" : "최종 승인 기록"}
                />
              ) : (
                <div className="pending">
                  최종 승인 조건: 시의성 평가(S4) 통과 · 미통과 단계 확인
                </div>
              )}
              <details className="editor">
                <summary>반려 기록</summary>
                <ReviewForm
                  id={id}
                  round="final"
                  decision="reject"
                  label="반려 기록"
                />
              </details>
            </>
          )}
          {me.roles.includes("expert") && (
            <>
              <h3>전문가 검토</h3>
              <ReviewForm
                id={id}
                round="expert"
                decision="approve"
                label="전문가 승인 기록"
              />
              <details className="editor">
                <summary>전문가 반려 기록</summary>
                <ReviewForm
                  id={id}
                  round="expert"
                  decision="reject"
                  label="전문가 반려 기록"
                />
              </details>
            </>
          )}
          {me.roles.includes("auditor") && (
            <>
              <h3>감사 검토</h3>
              <ReviewForm
                id={id}
                round="audit"
                decision="approve"
                label="감사 승인 기록"
              />
              <details className="editor">
                <summary>감사 반려 기록</summary>
                <ReviewForm
                  id={id}
                  round="audit"
                  decision="reject"
                  label="감사 반려 기록"
                />
              </details>
            </>
          )}
        </>
      )}
    </section>
  );
}
