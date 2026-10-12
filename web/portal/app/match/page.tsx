import Link from "next/link";
import { cleanQuery } from "@/lib/input";
import { explore, recentAnnouncements } from "@/lib/exploration";
import { CAUSE } from "@/lib/labels";
import { DiscoverySearch, IdeaCard, PageHeading } from "../components";
import { AnnouncementList } from "../announcement-list";

export const dynamic = "force-dynamic";

export default async function MatchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q: raw } = await searchParams;
  const q = cleanQuery(raw);
  const [recent, result] = await Promise.all([
    recentAnnouncements(),
    q.length >= 2 ? explore(q) : Promise.resolve(null),
  ]);
  return (
    <>
      <PageHeading eyebrow="탐색" title="주제·공고 매칭">
        제목·본문 유사도 · 검증 진단 · 시의성
      </PageHeading>
      <section className="card search-panel" aria-label="주제 검색">
        <DiscoverySearch
          id="match-query"
          query={q}
          help="2~200자 · 글자 유사도 검색 · 지원 자격·사업 적합성 별도 확인"
        />
        {recent.length > 0 && (
          <details className="recent-topics">
            <summary>수집 공고 선택</summary>
            <div className="chips">
              {recent.map((announcement) => (
                <Link
                  key={announcement.id}
                  href={`/match?q=${encodeURIComponent(announcement.title)}`}
                >
                  {announcement.title}
                </Link>
              ))}
            </div>
            <p className="muted">마감 공고 포함 · 접수 상태: 공고 원문 확인</p>
          </details>
        )}
      </section>
      <div className="match-layout section">
        <section aria-labelledby="match-results">
          <div className="section-heading">
            <h2 id="match-results">
              {result ? `“${q}” 검색 결과` : "검색 결과"}
            </h2>
            {result && (
              <span className="muted">
                {result.ideas.length}건
                {result.ideas.length >= 50 && " · 상위 50건"}
              </span>
            )}
          </div>
          {q && q.length < 2 && (
            <div className="notice error" role="status">
              검색어 최소 2자
            </div>
          )}
          {!result && !q && (
            <div className="pending">
              <strong>검색어 입력 대기</strong>
              <ul className="checklist">
                <li>검색 대상: 제목·본문</li>
                <li>결과 항목: 유사도·원인 진단·시의성</li>
              </ul>
              <Link className="text-link" href="/pool">
                전체 아이디어 →
              </Link>
            </div>
          )}
          {result &&
            (result.ideas.length ? (
              <div className="idea-grid match-grid">
                {result.ideas.map((idea) => (
                  <IdeaCard
                    key={idea.id}
                    id={idea.id}
                    title={idea.title}
                    meta={[
                      idea.year ?? "연도 미상",
                      idea.contest_name,
                      idea.award,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    cause={idea.cause}
                    score={idea.s}
                    verdict={idea.verdict}
                  >
                    <p className="muted">
                      글자 유사도 {idea.score.toFixed(2)} / 1.00
                    </p>
                  </IdeaCard>
                ))}
              </div>
            ) : (
              <div className="pending">
                <strong>검색 결과 없음</strong>
                <p className="muted">검색어 조정: 핵심 키워드</p>
                <Link className="link" href="/pool">
                  전체 아이디어
                </Link>
              </div>
            ))}
          {result && (
            <section
              className="card section"
              aria-labelledby="related-announcements"
            >
              <h2 id="related-announcements">관련 지원 공고</h2>
              {result.announcements.length ? (
                <AnnouncementList announcements={result.announcements} />
              ) : (
                <p className="muted">일치하는 공개 공고 없음</p>
              )}
            </section>
          )}
        </section>
        <aside className="stack">
          <section className="card reading-help">
            <h2>검색 기준</h2>
            <ul className="checklist">
              <li>유사도: 글자 일치 기반</li>
              <li>사업 적합성: 별도 검토</li>
              <li>미채점: 0점과 구분</li>
            </ul>
            <h2>시의성 판정</h2>
            <dl className="record-facts">
              <div>
                <dt>지금 가능</dt>
                <dd>S ≥ 4</dd>
              </div>
              <div>
                <dt>조건부</dt>
                <dd>3 ≤ S &lt; 4</dd>
              </div>
              <div>
                <dt>보류</dt>
                <dd>S &lt; 3 · 채점 축 2개 미만</dd>
              </div>
            </dl>
            {result && result.causes.length > 0 && (
              <>
                <h2>검증 진단 분포</h2>
                <ul className="search-causes">
                  {result.causes.map(({ cause, n }) => (
                    <li key={cause}>
                      <span>{CAUSE[cause] ?? cause}</span>
                      <strong>{n}건</strong>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <Link className="text-link" href="/stats">
              출처·통계 →
            </Link>
          </section>
          {!recent.length && (
            <section className="card">
              <h2>지원 공고 수집 현황</h2>
              <p className="muted">공개 공고 0건 · 제목 직접 검색 가능</p>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
