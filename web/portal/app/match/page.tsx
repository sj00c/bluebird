import Link from "next/link";
import { cleanQuery, explore, poolOverview, recentAnnouncements } from "@/lib/db";
import { CAUSE, VERDICT, VERDICT_PILL } from "@/lib/labels";

export const dynamic = "force-dynamic";

const CAUSE_ORDER = ["T", "D", "R", "M", "C", "O", "U"];

export default async function MatchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q: raw } = await searchParams;
  const q = cleanQuery(raw);
  const [o, recent, res] = await Promise.all([
    poolOverview(),
    recentAnnouncements(),
    q.length >= 2 ? explore(q) : Promise.resolve(null),
  ]);
  const causeTotal = o.causes.reduce((a, c) => a + c.n, 0);
  const causeN = new Map(o.causes.map((c) => [c.cause, c.n]));

  return (
    <div className="cols-b">
      {/* 왼쪽: 아이디어 풀 현황 */}
      <div className="card">
        <h2>아이디어 풀 현황</h2>
        <div className="kpi">
          <div><b>{o.ideas.toLocaleString("ko-KR")}</b><span>공개 아이디어</span></div>
          <div><b>{o.sources}</b><span>출처</span></div>
          <div><b>{o.traced.toLocaleString("ko-KR")}</b><span>흔적 판정 완료</span></div>
          <div><b>{o.revival.toLocaleString("ko-KR")}</b><span>재발굴 후보(S≥4.0)</span></div>
        </div>
        <h2>정체 원인 분포 <small>검증 완료 {causeTotal.toLocaleString("ko-KR")}건</small></h2>
        <div className="dist">
          {CAUSE_ORDER.map((c) => {
            const n = causeN.get(c) ?? 0;
            const pct = causeTotal ? Math.round((n / causeTotal) * 100) : 0;
            return (
              <div className="row" key={c}>
                <span className="c">{c}</span>
                <span>{CAUSE[c]}</span>
                <div className="tr"><div className={c === "U" ? "fl u" : "fl"} style={{ width: `${pct}%` }} /></div>
                <span className="v">{causeTotal ? `${pct}% (${n})` : "-"}</span>
              </div>
            );
          })}
        </div>
        <p className="note">
          ※ 원인 코드는 분류 뒤 담당자가 검증한 것만 셉니다. 표본 이중 코딩으로 일치도를 확인합니다(κ 목표 0.7 이상).
          판단 불가(U)는 따로 셉니다.
        </p>
      </div>

      {/* 오른쪽: 공고·주제 → 잠든 아이디어 */}
      <div className="card">
        <h2>신규 공고와 잠든 아이디어 매칭</h2>
        <form className="input" action="/match">
          <input name="q" aria-label="공고 제목 또는 주제" defaultValue={q} maxLength={200}
                 placeholder="공고 제목이나 주제를 넣으세요. 예: 소상공인 디지털 전환, 대체조제, 공공자전거" />
          <button type="submit">풀에서 찾기</button>
        </form>
        {recent.length > 0 ? (
          <div className="chips">
            {recent.map((a) => <Link key={a.id} href={`/match?q=${encodeURIComponent(a.title)}`}>{a.title}</Link>)}
          </div>
        ) : (
          <p className="muted" style={{ margin: "-4px 0 12px" }}>
            공고 자동 수집(K-Startup·기업마당)은 키 발급 뒤 시작합니다. 지금은 공고 제목을 직접 넣어 찾을 수 있습니다.
          </p>
        )}
        {q && q.length < 2 && <p className="muted">두 글자 이상 넣어 주세요.</p>}
        {!res && !q && (
          <div className="pending">공고 제목이나 관심 주제를 넣으면, 비슷한 과거 아이디어와 그 아이디어가 왜 막혔는지, 지금은 해볼 만한지를 함께 보여 줍니다.</div>
        )}
        {res && (
          res.ideas.length === 0 ? (
            <div className="pending">비슷한 아이디어를 찾지 못했습니다. 다른 낱말로 넣어 보세요.</div>
          ) : (
            <>
              <table>
                <thead>
                  <tr><th>#</th><th>아이디어(익명 처리)</th><th>제출</th><th className="num">유사도</th><th>원인</th><th className="num">시의성 S</th><th>판정</th></tr>
                </thead>
                <tbody>
                  {res.ideas.map((i, n) => (
                    <tr key={i.id}>
                      <td className="nw">{n + 1}</td>
                      <td>
                        <Link className="n" href={`/ideas/${i.id}`}>{i.title}</Link>
                        <span className="s">{i.contest_name}{i.award ? ` · ${i.award}` : ""}</span>
                      </td>
                      <td className="nw">{i.year ?? "-"}</td>
                      <td className="num">{i.score.toFixed(2)}</td>
                      <td className="nw">{i.cause ? <span className={`cd ${i.cause}`} title={CAUSE[i.cause]}>{i.cause}</span> : <span className="muted">-</span>}</td>
                      <td className="sc num">{i.s != null ? Number(i.s).toFixed(1) : <span className="muted">-</span>}</td>
                      <td className="nw">
                        {i.verdict ? (
                          <span className={`pill ${VERDICT_PILL[i.verdict] ?? "lo"}`}>{VERDICT[i.verdict] ?? i.verdict}</span>
                        ) : (
                          <span className="pill lo">검증 대기</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {res.announcements.length > 0 && (
                <>
                  <h2>관련 지원 공고</h2>
                  <table>
                    <tbody>
                      {res.announcements.map((a) => (
                        <tr key={a.id}>
                          <td><a className="link" href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a></td>
                          <td className="muted nw">{a.org ?? "-"}{a.apply_to && ` · 마감 ${a.apply_to}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </>
          )
        )}
        <p className="note">
          판정 기준: S≥4.0 지금 가능 / 3.0~3.9 조건부(원인 해소 조건 명시) / 3.0 미만 보류. 원인·점수는 담당자 검증을 마친
          아이디어에만 표시되고, 각 점수에는 근거 문서 링크가 붙습니다. 유사도는 제목·본문 글자 겹침(0~1)입니다.
          {res && res.ideas.length >= 50 && " 상위 50건만 보여 줍니다."}
        </p>
      </div>
    </div>
  );
}
