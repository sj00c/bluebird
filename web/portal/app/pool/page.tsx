import Link from "next/link";
import { cleanQuery, MAX_PAGE, PAGE_SIZE, parsePage } from "@/lib/input";
import { listIdeas, sourceList } from "@/lib/ideas";
import { IdeaCard, PageHeading } from "../components";
import { PoolFilters } from "./pool-filters";

type SearchParams = Promise<{
  q?: string;
  year?: string;
  source?: string;
  verified?: string;
  page?: string;
}>;

export const dynamic = "force-dynamic";

export default async function PoolPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const sp = await searchParams;
  const q = cleanQuery(sp.q);
  const year =
    typeof sp.year === "string" && /^\d{4}$/.test(sp.year)
      ? Number(sp.year)
      : undefined;
  const sources = await sourceList();
  const source = sources.some((item) => item.id === sp.source)
    ? sp.source
    : undefined;
  const verified = sp.verified === "1";
  const page = parsePage(sp.page);
  const { total, rows } = await listIdeas({ q, year, source, verified, page });
  const pages = Math.max(1, Math.min(MAX_PAGE, Math.ceil(total / PAGE_SIZE)));
  const pageQuery = (nextPage: number) =>
    new URLSearchParams({
      ...(q && { q }),
      ...(year && { year: String(year) }),
      ...(source && { source }),
      ...(verified && { verified: "1" }),
      page: String(nextPage),
    });

  return (
    <>
      <PageHeading eyebrow="공개 데이터" title="아이디어 풀">
        제목 검색 · 출처·연도 필터 · 검증 진단 구분
      </PageHeading>
      <PoolFilters
        query={q}
        year={year}
        source={source}
        verified={verified}
        sources={sources}
      />
      <div className="section-heading results-heading">
        <h2>
          검색 결과{" "}
          <span className="result-count">
            {total.toLocaleString("ko-KR")}건
          </span>
        </h2>
        <p className="muted">연도 최신순 · 한 페이지 {PAGE_SIZE}건</p>
      </div>
      {rows.length ? (
        <div className="idea-grid pool-grid">
          {rows.map((idea) => (
            <IdeaCard
              key={idea.id}
              id={idea.id}
              title={idea.title}
              meta={[idea.year ?? "연도 미상", idea.contest_name, idea.award]
                .filter(Boolean)
                .join(" · ")}
              cause={idea.cause}
              score={idea.s}
              verdict={idea.verdict}
            >
              <p className="muted">
                {idea.source_name}
                {idea.category && ` · ${idea.category}`}
                {!idea.body && " · 본문 미공개"}
              </p>
            </IdeaCard>
          ))}
        </div>
      ) : (
        <div className="pending">
          <strong>{total ? "페이지 결과 없음" : "검색 결과 없음"}</strong>
          <p>
            {total ? (
              <Link className="link" href={`/pool?${pageQuery(1)}`}>
                첫 페이지
              </Link>
            ) : (
              <Link className="link" href="/pool">
                필터 초기화
              </Link>
            )}
          </p>
        </div>
      )}
      <nav className="pager" aria-label="검색 결과 페이지">
        {page > 1 && (
          <Link href={`/pool?${pageQuery(Math.min(page - 1, pages))}`}>
            ← 이전
          </Link>
        )}
        <span aria-current="page">
          {page.toLocaleString("ko-KR")} / {pages.toLocaleString("ko-KR")}{" "}
          페이지
        </span>
        {page < pages && (
          <Link href={`/pool?${pageQuery(page + 1)}`}>다음 →</Link>
        )}
      </nav>
      <ul className="checklist note">
        <li>개인정보: 적재 시 익명 처리</li>
        <li>진단·점수 미표시: 검증 분석 미공개</li>
      </ul>
    </>
  );
}
