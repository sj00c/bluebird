import type { Detail } from "@/lib/contracts";
import { cause, DECISIONS, ROUNDS, when } from "@/lib/labels";

export function ReviewHistory({ detail: d }: { detail: Detail }) {
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
    </section>
  );
}
