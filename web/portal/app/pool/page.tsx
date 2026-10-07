import Link from "next/link";
import { listIdeas, PAGE_SIZE } from "@/lib/db";

type SP = Promise<{ q?: string; year?: string; page?: string }>;

export default async function PoolPage({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const q = (sp.q ?? "").trim().slice(0, 100);
  const year = /^\d{4}$/.test(sp.year ?? "") ? Number(sp.year) : undefined;
  const page = Math.max(1, Number(sp.page) || 1);
  const { total, rows } = await listIdeas({ q: q || undefined, year, page });
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const qs = (p: number) => new URLSearchParams({ ...(q && { q }), ...(year && { year: String(year) }), page: String(p) });

  return (
    <div className="card">
      <form className="filters" action="/pool">
        <input name="q" defaultValue={q} placeholder="아이디어 제목 검색" />
        <input name="year" defaultValue={year ?? ""} placeholder="연도" style={{ flex: "0 0 90px" }} />
        <button type="submit">검색</button>
      </form>
      <p className="muted">검색 결과 {total.toLocaleString("ko-KR")}건</p>
      <table>
        <thead>
          <tr><th style={{ width: 70 }}>연도</th><th>아이디어</th><th style={{ width: 220 }}>공모전 · 수상</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.year ?? "-"}</td>
              <td>
                <Link href={`/ideas/${encodeURIComponent(r.id)}`}>{r.title}</Link>
                <div className="muted">{r.id}{r.category && ` · ${r.category}`}</div>
              </td>
              <td>
                {r.host_org || r.contest_name}
                <div className="muted">{r.award ?? ""}</div>
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
