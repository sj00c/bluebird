import Link from "next/link";
import { getWeeklyTop, type TopRow } from "@/lib/db";
import { CAUSE, CHANGE_KIND, VERDICT } from "@/lib/labels";

export const dynamic = "force-dynamic";

function Row({ r }: { r: TopRow }) {
  return (
    <tr>
      <td className="rank">{r.rank}</td>
      <td>
        <Link href={`/ideas/${r.idea_id}`}>{r.title}</Link>
        <div className="muted">{r.year ?? "-"} · {r.contest_name}</div>
      </td>
      <td>{r.cause ? `${r.cause} ${CAUSE[r.cause] ?? ""}` : "-"}</td>
      <td>
        {r.change_title ? (
          <>
            <span className="tag">{CHANGE_KIND[r.change_kind ?? ""] ?? r.change_kind}</span>
            {r.change_title}
          </>
        ) : "-"}
      </td>
      <td>{r.verdict ? <span className="verdict">{VERDICT[r.verdict] ?? r.verdict}</span> : "-"}{r.s != null && `S ${Number(r.s).toFixed(1)}`}</td>
    </tr>
  );
}

export default async function Home() {
  const { week, rows } = await getWeeklyTop();
  const head = (
    <thead>
      <tr><th>#</th><th>아이디어</th><th>막힌 이유</th><th>바뀐 것</th><th>지금</th></tr>
    </thead>
  );
  return (
    <div className="card">
      <h1>이번 주 재조명</h1>
      <p className="muted">
        막혔던 이유가 풀렸을 수 있는 과거 공모전 아이디어입니다. 담당자가 근거를 확인하고 승인한 것만 올립니다.
        {week && ` · ${week} 주`}
      </p>
      {rows.length === 0 ? (
        <div className="pending">이번 주에 올릴 만큼 검증을 마친 아이디어가 아직 없습니다. <Link href="/explore">주제로 찾아보기</Link></div>
      ) : (
        <>
          <table>{head}<tbody>{rows.slice(0, 10).map((r) => <Row key={r.rank} r={r} />)}</tbody></table>
          {rows.length > 10 && (
            <details className="more">
              <summary>11–{rows.length}위 펼치기</summary>
              <table>{head}<tbody>{rows.slice(10).map((r) => <Row key={r.rank} r={r} />)}</tbody></table>
            </details>
          )}
        </>
      )}
      <p className="muted" style={{ marginTop: 12 }}>
        전체 아이디어는 <Link href="/pool">아이디어 풀</Link>, 주제·공고로 찾으려면 <Link href="/explore">주제·공고 넣기</Link>.
      </p>
    </div>
  );
}
