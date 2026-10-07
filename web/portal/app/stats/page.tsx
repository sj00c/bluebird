import { cardKindStats, poolOverview, sourceStats, yearStats } from "@/lib/db";
import { CAUSE, VERDICT } from "@/lib/labels";

export const dynamic = "force-dynamic";

const CARD_KIND: Record<string, string> = {
  full: "전체 카드(AI 요약)",
  local_extract: "본문 규칙 추출",
  title_only: "제목만",
};

function Bars({ rows }: { rows: { label: string; n: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  const total = rows.reduce((a, r) => a + r.n, 0);
  return (
    <div className="dist wide">
      {rows.map((r) => (
        <div className="row" key={r.label}>
          <span>{r.label}</span>
          <div className="tr"><div className="fl" style={{ width: `${(r.n / max) * 100}%` }} /></div>
          <span className="v">{r.n.toLocaleString("ko-KR")} ({total ? Math.round((r.n / total) * 100) : 0}%)</span>
        </div>
      ))}
    </div>
  );
}

export default async function StatsPage() {
  const [o, sources, years, kinds] = await Promise.all([poolOverview(), sourceStats(), yearStats(), cardKindStats()]);
  return (
    <>
      <div className="card">
        <h2>공개 현황</h2>
        <div className="kpi k6">
          <div><b>{o.ideas.toLocaleString("ko-KR")}</b><span>공개 아이디어</span></div>
          <div><b>{o.sources}</b><span>출처</span></div>
          <div><b>{o.externalSearched.toLocaleString("ko-KR")}</b><span>외부 흔적 검색</span></div>
          <div><b>{o.verified.toLocaleString("ko-KR")}</b><span>원인 진단 검증</span></div>
          <div><b>{o.scored.toLocaleString("ko-KR")}</b><span>시의성 채점</span></div>
          <div><b>{o.announcements.toLocaleString("ko-KR")}</b><span>수집 공고</span></div>
        </div>
        <p className="note">공개 DB 기준입니다. 공개가 보류된 출처(약관 확인 중)의 아이디어는 세지 않습니다.</p>
      </div>

      <div className="cols-b">
        <div className="stack">
          <div className="card">
            <h2>카드 종류</h2>
            <Bars rows={kinds.map((k) => ({ label: CARD_KIND[k.card_kind] ?? k.card_kind, n: k.n }))} />
          </div>
          <div className="card">
            <h2>정체 원인 <small>검증 {o.verified}건</small></h2>
            {o.causes.length === 0 ? <p className="muted">아직 없습니다.</p> : (
              <Bars rows={o.causes.map((c) => ({ label: `${c.cause} ${CAUSE[c.cause] ?? ""}`, n: c.n }))} />
            )}
            <h2>시의성 판정 <small>채점 {o.scored}건</small></h2>
            {o.verdicts.length === 0 ? <p className="muted">아직 없습니다.</p> : (
              <Bars rows={o.verdicts.map((v) => ({ label: VERDICT[v.verdict] ?? v.verdict, n: v.n }))} />
            )}
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <h2>출처별</h2>
            <table>
              <thead>
                <tr><th>출처</th><th>이용 조건</th><th className="num">아이디어</th><th className="num">본문 있음</th><th>연도</th></tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id}>
                    <td><a className="link" href={s.url} target="_blank" rel="noopener noreferrer">{s.name}</a></td>
                    <td className="muted">{s.license}</td>
                    <td className="num">{s.ideas.toLocaleString("ko-KR")}</td>
                    <td className="num">{s.ideas ? Math.round((s.with_body / s.ideas) * 100) : 0}%</td>
                    <td className="nw">{s.y_min ?? "-"}–{s.y_max ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card">
            <h2>제출 연도별</h2>
            <Bars rows={years.map((y) => ({ label: String(y.year), n: y.n }))} />
          </div>
        </div>
      </div>
    </>
  );
}
