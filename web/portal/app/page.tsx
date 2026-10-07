import Link from "next/link";
import { getWeeklyTop, poolOverview, verifiedCards, type TopRow, type VerifiedCard } from "@/lib/db";
import { CAUSE, CHANGE_KIND, VERDICT, VERDICT_PILL } from "@/lib/labels";

export const dynamic = "force-dynamic";

function Verdict({ v }: { v: string | null }) {
  return v ? <span className={`pill ${VERDICT_PILL[v] ?? "lo"}`}>{VERDICT[v] ?? v}</span> : <span className="pill lo">미평가</span>;
}

function ChangeCell({ title, kind }: { title: string | null; kind: string | null }) {
  if (!title) return <span className="muted">-</span>;
  return (
    <>
      <span className="tag g">{CHANGE_KIND[kind ?? ""] ?? kind}</span> <span className="s">{title}</span>
    </>
  );
}

function TopRowView({ r }: { r: TopRow }) {
  return (
    <tr>
      <td className="rank">{r.rank}</td>
      <td>
        <Link className="n" href={`/ideas/${r.idea_id}`}>{r.title}</Link>
        <span className="s">{r.year ?? "-"} · {r.contest_name}</span>
      </td>
      <td className="nw">{r.cause ? <><span className={`cd ${r.cause}`}>{r.cause}</span> {CAUSE[r.cause]}</> : "-"}</td>
      <td><ChangeCell title={r.change_title} kind={r.change_kind} /></td>
      <td className="sc num">{r.s != null ? Number(r.s).toFixed(1) : "-"}</td>
      <td className="nw"><Verdict v={r.verdict} /></td>
    </tr>
  );
}

function CardRow({ c }: { c: VerifiedCard }) {
  return (
    <tr>
      <td>
        <Link className="n" href={`/ideas/${c.idea_id}`}>{c.title}</Link>
        <span className="s">{c.year ?? "-"} · {c.contest_name}{c.award && ` · ${c.award}`}</span>
      </td>
      <td className="nw">
        <span className={`cd ${c.cause}`}>{c.cause}</span> {CAUSE[c.cause]}
        {c.secondary && <span className="s">보조 {c.secondary} {CAUSE[c.secondary]}</span>}
      </td>
      <td><ChangeCell title={c.change_title} kind={c.change_kind} />{c.changes > 1 && <span className="s">외 {c.changes - 1}건</span>}</td>
      <td className="sc num">{c.s != null ? Number(c.s).toFixed(1) : "-"}</td>
      <td className="nw"><Verdict v={c.verdict} /></td>
    </tr>
  );
}

const topHead = (
  <thead>
    <tr><th>#</th><th>아이디어(익명 처리)</th><th>막힌 이유</th><th>무엇이 달라졌나</th><th className="num">시의성 S</th><th>판정</th></tr>
  </thead>
);

export default async function CardsPage() {
  const [{ week, rows }, cards, o] = await Promise.all([getWeeklyTop(), verifiedCards(), poolOverview()]);
  return (
    <>
      <div className="card">
        <div className="kpi k6">
          <div><b>{o.ideas.toLocaleString("ko-KR")}</b><span>공개 아이디어</span></div>
          <div><b>{o.traced.toLocaleString("ko-KR")}</b><span>사업화 흔적 판정</span></div>
          <div><b>{o.verified.toLocaleString("ko-KR")}</b><span>원인 진단 검증</span></div>
          <div><b>{o.changes.toLocaleString("ko-KR")}</b><span>바뀐 것 연결</span></div>
          <div><b>{o.scored.toLocaleString("ko-KR")}</b><span>시의성 채점</span></div>
          <div><b>{o.revival.toLocaleString("ko-KR")}</b><span>재발굴 후보(S≥4.0)</span></div>
        </div>
        <h2>이번 주 재조명 <small>{week ? `${week} 주 · ` : ""}담당자가 근거를 확인하고 승인한 것만</small></h2>
        {rows.length === 0 ? (
          <div className="pending">
            이번 주에 올릴 만큼 검증을 마친 아이디어가 아직 없습니다. <Link className="link" href="/match">주제로 찾아보기</Link>
          </div>
        ) : (
          <>
            <table>{topHead}<tbody>{rows.slice(0, 10).map((r) => <TopRowView key={r.rank} r={r} />)}</tbody></table>
            {rows.length > 10 && (
              <details className="more">
                <summary>11–{rows.length}위 펼치기</summary>
                <table>{topHead}<tbody>{rows.slice(10).map((r) => <TopRowView key={r.rank} r={r} />)}</tbody></table>
              </details>
            )}
          </>
        )}
      </div>

      <div className="card">
        <h2>진단 카드 전체 <small>원인 진단이 검증된 {cards.length}건 · 시의성 높은 순</small></h2>
        {cards.length === 0 ? (
          <div className="pending">검증을 마친 진단 카드가 아직 없습니다.</div>
        ) : (
          <table>
            <thead>
              <tr><th>아이디어(익명 처리)</th><th>막힌 이유</th><th>무엇이 달라졌나</th><th className="num">시의성 S</th><th>판정</th></tr>
            </thead>
            <tbody>{cards.map((c) => <CardRow key={c.idea_id} c={c} />)}</tbody>
          </table>
        )}
        <p className="note">
          나머지 {(o.ideas - cards.length).toLocaleString("ko-KR")}건은 <Link className="link" href="/pool">아이디어 풀</Link>에서
          원본을 볼 수 있고, 원인 진단은 담당자 검증 뒤에 공개됩니다.
        </p>
      </div>
    </>
  );
}
