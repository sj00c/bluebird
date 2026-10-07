import Link from "next/link";
import { listIdeas, PAGE_SIZE, sourceList } from "@/lib/db";
import { CAUSE, VERDICT, VERDICT_PILL } from "@/lib/labels";

type SP = Promise<{ q?: string; year?: string; source?: string; verified?: string; page?: string }>;

export const dynamic = "force-dynamic";

export default async function PoolPage({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const q = (sp.q ?? "").trim().slice(0, 100);
  const year = /^\d{4}$/.test(sp.year ?? "") ? Number(sp.year) : undefined;
  const sources = await sourceList();
  const source = sources.some((s) => s.id === sp.source) ? sp.source : undefined;
  const verified = sp.verified === "1";
  const page = Math.max(1, Number(sp.page) || 1);
  const { total, rows } = await listIdeas({ q: q || undefined, year, source, verified, page });
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const qs = (p: number) =>
    new URLSearchParams({
      ...(q && { q }),
      ...(year && { year: String(year) }),
      ...(source && { source }),
      ...(verified && { verified: "1" }),
      page: String(p),
    });

  return (
    <div className="card">
      <h2>아이디어 풀 <small>공개 아이디어 원본 · 이름은 적재할 때 지우고 익명 ID만 남깁니다</small></h2>
      <form className="input" action="/pool">
        <input name="q" defaultValue={q} placeholder="아이디어 제목 검색" aria-label="제목 검색" />
        <select name="source" defaultValue={source ?? ""} aria-label="출처">
          <option value="">출처 전체</option>
          {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <input name="year" defaultValue={year ?? ""} placeholder="연도" aria-label="연도" style={{ flex: "0 0 90px" }} />
        <select name="verified" defaultValue={verified ? "1" : ""} aria-label="검증 상태">
          <option value="">전체</option>
          <option value="1">진단 검증된 것만</option>
        </select>
        <button type="submit">검색</button>
      </form>
      <p className="muted" style={{ marginBottom: 8 }}>검색 결과 {total.toLocaleString("ko-KR")}건</p>
      <table>
        <thead>
          <tr><th style={{ width: 70 }}>제출</th><th>아이디어(익명 처리)</th><th>공모전 · 수상</th><th>원인</th><th className="num">시의성 S</th><th>판정</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="nw">{r.year ?? "-"}</td>
              <td>
                <Link className="n" href={`/ideas/${encodeURIComponent(r.id)}`}>{r.title}</Link>
                <span className="s">{r.id}{r.category && ` · ${r.category}`}{!r.body && " · 본문 없음"}</span>
              </td>
              <td>
                {r.contest_name}
                <span className="s">{[r.host_org, r.award].filter(Boolean).join(" · ")}</span>
              </td>
              <td className="nw">{r.cause ? <span className={`cd ${r.cause}`} title={CAUSE[r.cause]}>{r.cause}</span> : <span className="muted">-</span>}</td>
              <td className="sc num">{r.s != null ? Number(r.s).toFixed(1) : <span className="muted">-</span>}</td>
              <td className="nw">
                {r.verdict ? (
                  <span className={`pill ${VERDICT_PILL[r.verdict] ?? "lo"}`}>{VERDICT[r.verdict] ?? r.verdict}</span>
                ) : (
                  <span className="pill lo">검증 대기</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pager">
        {page > 1 && <Link href={`/pool?${qs(page - 1)}`}>이전</Link>}
        <span className="muted">{page} / {pages}</span>
        {page < pages && <Link href={`/pool?${qs(page + 1)}`}>다음</Link>}
      </div>
    </div>
  );
}
