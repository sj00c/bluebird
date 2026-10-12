import Link from "next/link";
import type { Detail, Me } from "@/lib/contracts";
import {
  cause,
  DECISIONS,
  OBJECTION_KINDS,
  OBJECTION_STATUS,
  ROUNDS,
  when,
} from "@/lib/labels";

export function ReviewHistory({ detail: d, me }: { detail: Detail; me: Me }) {
  return (
    <section className="card" id="history">
      <h2>검토 이력</h2>
      {d.reviews.length ? (
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="검토 이력"
        >
          <table>
            <thead>
              <tr>
                <th>검토 라운드</th>
                <th>검토자</th>
                <th>결정</th>
                <th>메모</th>
                <th>시각</th>
              </tr>
            </thead>
            <tbody>
              {d.reviews.map((r, i) => (
                <tr key={i}>
                  <td>{ROUNDS[r.round] ?? r.round}</td>
                  <td>{r.reviewer}</td>
                  <td>
                    <span className="tag">
                      {DECISIONS[r.decision] ?? r.decision}
                    </span>
                    {r.code && cause(r.code)}
                  </td>
                  <td>
                    {r.note ? (
                      <details>
                        <summary>검토 메모</summary>
                        <div className="body">{r.note}</div>
                      </details>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="nowrap">{when(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="pending">검토 기록 없음</div>
      )}
      {me.roles.some((r) => ["reviewer", "auditor"].includes(r)) && (
        <>
          <div className="section-heading">
            <h3>접수된 이의</h3>
            <Link className="lnk" href="/objections">
              이의 관리 →
            </Link>
          </div>
          {d.objections.length ? (
            d.objections.map((o) => (
              <article key={o.id} className="evidence">
                <span className="tag">{OBJECTION_KINDS[o.kind] ?? o.kind}</span>
                <span className="tag">
                  {OBJECTION_STATUS[o.status] ?? o.status}
                </span>
                <p className="muted">
                  접수 {when(o.submitted_at)}
                  {o.resolved_at && ` · 처리 ${when(o.resolved_at)}`}
                </p>
                <details>
                  <summary>이의 내용·처리 기록</summary>
                  <div className="body">{o.body}</div>
                  {o.resolution && (
                    <p className="prewrap">처리 내용: {o.resolution}</p>
                  )}
                </details>
              </article>
            ))
          ) : (
            <div className="pending">접수된 이의 없음</div>
          )}
        </>
      )}
    </section>
  );
}
