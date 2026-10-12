import Link from "next/link";
import { listIdeas, sourceList } from "@/lib/ideas";
import { getWeeklyTop } from "@/lib/revival";
import { RecordWorkbench } from "./record-workbench";
import { WeeklyReadingList } from "./weekly-reading-list";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [{ total, rows: recent }, sources, weekly] = await Promise.all([
    listIdeas({ page: 1 }, 8),
    sourceList(),
    getWeeklyTop(),
  ]);
  const records = recent.map(
    ({
      id,
      title,
      year,
      source_name,
      contest_name,
      award,
      cause,
      verdict,
      s,
    }) => ({
      id,
      title,
      year,
      source_name,
      contest_name,
      award,
      cause,
      verdict,
      s,
    }),
  );

  return (
    <>
      <header className="workbench-heading">
        <div>
          <p className="eyebrow">PUBLIC IDEA WORKSPACE</p>
          <h1>
            아이디어 작업대
            <span className="heading-dot" aria-hidden="true">
              .
            </span>
          </h1>
        </div>
        <div className="workspace-total">
          <strong>{total.toLocaleString("ko-KR")}</strong>
          <span>공개 아이디어</span>
        </div>
      </header>
      <form
        action="/pool"
        method="get"
        className="workspace-search"
        aria-label="공개 아이디어 검색"
      >
        <div className="workspace-query">
          <label htmlFor="home-q">제목 검색</label>
          <input
            id="home-q"
            name="q"
            maxLength={200}
            placeholder="제목 또는 키워드"
          />
          <button type="submit">
            검색 <span aria-hidden="true">↗</span>
          </button>
        </div>
        <details className="workspace-filters">
          <summary>
            검색 조건 <span className="muted">출처 · 연도 · 검증</span>
          </summary>
          <div className="filter-form home-filter">
            <label htmlFor="home-source">
              출처
              <select id="home-source" name="source" defaultValue="">
                <option value="">모든 출처</option>
                {sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.name}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="home-year">
              제출 연도
              <input
                id="home-year"
                name="year"
                inputMode="numeric"
                pattern="[0-9]{4}"
                maxLength={4}
                placeholder="YYYY"
              />
            </label>
            <label htmlFor="home-verified">
              진단 검증
              <select id="home-verified" name="verified" defaultValue="">
                <option value="">공개 원본 전체</option>
                <option value="1">검증된 진단만</option>
              </select>
            </label>
          </div>
        </details>
      </form>
      <RecordWorkbench records={records} total={total} />
      <div className="workspace-secondary">
        <WeeklyReadingList week={weekly.week} rows={weekly.rows} />
        <section className="workspace-tools" aria-labelledby="review-title">
          <p className="eyebrow">04 / 검토 도구</p>
          <h2 id="review-title">검토 바로가기</h2>
          <div className="action-list">
            <Link href="/match">
              <span>주제·공고 매칭</span>
              <span aria-hidden="true">↗</span>
            </Link>
            <Link href="/pool?verified=1">
              <span>검증된 진단</span>
              <span aria-hidden="true">↗</span>
            </Link>
            <Link href="/timeliness">
              <span>시의성 평가</span>
              <span aria-hidden="true">↗</span>
            </Link>
            <Link href="/stats">
              <span>출처·공개 범위</span>
              <span aria-hidden="true">↗</span>
            </Link>
          </div>
        </section>
      </div>
    </>
  );
}
