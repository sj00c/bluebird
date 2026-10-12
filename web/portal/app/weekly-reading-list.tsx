import type { TopRow } from "@/lib/types";
import Link from "next/link";
import { Verdict } from "./components";

export function WeeklyReadingList({
  week,
  rows,
}: {
  week: string | null;
  rows: TopRow[];
}) {
  return (
    <section className="weekly-panel" aria-labelledby="weekly-title">
      <p className="eyebrow">03 / 주간 기록</p>
      <div className="section-heading">
        <h2 id="weekly-title">주간 선정</h2>
        <span className="result-count">{rows.length}건</span>
      </div>
      <p className="muted">{week ? `${week} 기준` : "선정 내역 없음"}</p>
      {rows.length ? (
        <ol className="weekly-list">
          {rows.map((row) => (
            <li key={row.idea_id}>
              <span className="weekly-rank" aria-label={`선정 ${row.rank}위`}>
                {String(row.rank).padStart(2, "0")}
              </span>
              <div>
                <h3>
                  <Link href={`/ideas/${encodeURIComponent(row.idea_id)}`}>
                    {row.title}
                  </Link>
                </h3>
                <div className="weekly-status">
                  <Verdict value={row.verdict} />
                  <span className="muted">
                    {row.s != null
                      ? `${Number(row.s).toFixed(1)} / 5.0`
                      : "미채점"}
                  </span>
                </div>
                {row.change_title && (
                  <details className="more">
                    <summary>연결된 변화</summary>
                    <p>{row.change_title}</p>
                  </details>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="pending">
          <strong>공개된 선정 목록 없음</strong>
        </div>
      )}
      <Link className="text-link" href="/timeliness">
        시의성 전체 <span aria-hidden="true">→</span>
      </Link>
    </section>
  );
}
