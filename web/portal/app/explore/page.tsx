import Link from "next/link";
import { cleanQuery, explore } from "@/lib/db";
import { CAUSE, VERDICT } from "@/lib/labels";

export const dynamic = "force-dynamic";

export default async function Explore({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q: raw } = await searchParams;
  const q = cleanQuery(raw);
  const res = q.length >= 2 ? await explore(q) : null;
  const ready = res?.ideas.filter((i) => i.verdict) ?? [];
  const diagnosed = res?.ideas.filter((i) => i.cause).length ?? 0;
  return (
    <div className="card">
      <h1>주제·공고 넣기</h1>
      <p className="muted">관심 주제나 공고 제목을 넣으면 비슷한 과거 아이디어와, 그 아이디어들이 왜 막혔는지를 보여 줍니다.</p>
      <form className="filters" action="/explore">
        <input name="q" aria-label="주제 또는 공고 제목" defaultValue={q} placeholder="예: 대체조제, 만성질환 관리, 공공자전거" maxLength={200} />
        <button type="submit">찾기</button>
      </form>
      {q && q.length < 2 && <p className="muted">두 글자 이상 넣어 주세요.</p>}
      {res && (
        <>
          <h2>지금 가능한 후보</h2>
          {ready.length === 0 ? (
            <p className="muted">이 주제로 담당자 검증까지 마친 아이디어는 아직 없습니다.</p>
          ) : (
            ready.map((i) => (
              <p key={i.id}>
                <span className="verdict">{VERDICT[i.verdict!] ?? i.verdict}</span>
                <Link href={`/ideas/${i.id}`}>{i.title}</Link>
                {i.s != null && <span className="muted"> · S {Number(i.s).toFixed(1)}</span>}
              </p>
            ))
          )}
          <h2>막힌 이유 분포</h2>
          {diagnosed === 0 ? (
            <p className="muted">비슷한 아이디어 {res.ideas.length}건 중 막힌 이유가 검증·공개된 것은 아직 없습니다.</p>
          ) : (
            <p>
              {res.causes.map((c) => (
                <span key={c.cause} className="tag">{c.cause} {CAUSE[c.cause] ?? c.cause} {c.n}건</span>
              ))}
              <span className="muted"> (비슷한 아이디어 {res.ideas.length}건 중 검증된 {diagnosed}건 기준)</span>
            </p>
          )}
          {res.announcements.length > 0 && (
            <>
              <h2>관련 지원 공고</h2>
              {res.announcements.map((a) => (
                <p key={a.id}>
                  <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
                  <span className="muted"> · {a.org ?? "-"}{a.apply_to && ` · 마감 ${a.apply_to}`}</span>
                </p>
              ))}
            </>
          )}
          <h2>선행 아이디어 {res.ideas.length}건{res.ideas.length >= 50 && " (상위 50)"}</h2>
          {res.ideas.length === 0 ? (
            <p className="muted">비슷한 아이디어를 찾지 못했습니다. 다른 낱말로 넣어 보세요.</p>
          ) : (
            <table>
              <thead><tr><th>아이디어</th><th>연도</th><th>막힌 이유</th><th>유사도</th></tr></thead>
              <tbody>
                {res.ideas.map((i) => (
                  <tr key={i.id}>
                    <td><Link href={`/ideas/${i.id}`}>{i.title}</Link><div className="muted">{i.contest_name}{i.award ? ` · ${i.award}` : ""}</div></td>
                    <td className="nw">{i.year ?? "-"}</td>
                    <td className="nw">{i.cause ? `${i.cause} ${CAUSE[i.cause] ?? ""}` : <span className="muted">검증 대기</span>}</td>
                    <td className="nw">{i.score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
