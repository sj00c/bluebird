import Link from "next/link";
import type { Queue, QueueItem } from "@/lib/contracts";
import { cause, QUEUE_STAGES, STAGE_NAMES, VERDICTS } from "@/lib/labels";

function QueueRow({ item }: { item: QueueItem }) {
  const href = `/ideas/${encodeURIComponent(item.idea_id)}`;
  return (
    <li className="queue-row">
      <div className="queue-identity">
        <Link className="idea-title" href={href}>
          {item.title}
        </Link>
        <span className="muted mono">{item.idea_id}</span>
      </div>
      <dl className="queue-facts">
        <div>
          <dt>연도 · 출처</dt>
          <dd>
            {item.year ?? "연도 미상"}
            <small>{item.source_id}</small>
          </dd>
        </div>
        <div>
          <dt>막힌 이유</dt>
          <dd>{item.cause ? cause(item.cause) : "미진단"}</dd>
        </div>
        <div>
          <dt>시의성</dt>
          <dd>
            {item.s ?? "미평가"}
            <small>
              {item.verdict
                ? (VERDICTS[item.verdict] ?? item.verdict)
                : "판정 미기록"}
            </small>
          </dd>
        </div>
      </dl>
      <Link
        className="button sub small"
        href={href}
        aria-label={`${item.title} 상세 보기`}
      >
        상세 보기 →
      </Link>
    </li>
  );
}

export function QueueWorkbench({
  queue,
  stage,
  query,
  canAuthor,
}: {
  queue: Queue;
  stage: string;
  query: string;
  canAuthor: boolean;
}) {
  const isRaw = stage === "raw";
  const href = (selected: string, offset = 0) =>
    `/?${new URLSearchParams({ stage: selected, q: query, offset: String(offset) })}`;
  return (
    <>
      <header className="page-heading">
        <div>
          <h1>검토 대기열</h1>
        </div>
        <Link className="button sub" href="/overview">
          운영 개요
        </Link>
      </header>
      <nav className="stage-tabs" aria-label="수집 원본 및 검토 단계">
        {QUEUE_STAGES.map((item, index) => (
          <Link
            key={item}
            href={href(item)}
            className={stage === item ? "on" : ""}
            aria-current={stage === item ? "page" : undefined}
          >
            <small>{item === "raw" ? "원본" : String(index).padStart(2, "0")}</small>
            <b>{STAGE_NAMES[item]}</b>
            <span>
              {item === "raw" ? "전체" : "누적"}{" "}
              {(queue.counts[item] ?? 0).toLocaleString("ko-KR")}
            </span>
          </Link>
        ))}
      </nav>
      <section className="card queue-card">
        <div className="section-heading">
          <div>
            <h2>{STAGE_NAMES[stage]} {isRaw ? "목록" : "통과 목록"}</h2>
            <span className="muted">
              {isRaw
                ? "카드·분석 생성 여부와 무관한 원본"
                : canAuthor ? "분석 작성·최종 검토" : "역할별 검토"}
            </span>
          </div>
          <span className="tag">
            검색 결과 {queue.total.toLocaleString("ko-KR")}건
          </span>
        </div>
        <ul className="instructions">
          <li>
            {isRaw
              ? "공개 중단 자료 제외 · 카드·진단·평가 미작성 자료 포함"
              : stage === "s5"
                ? "최종 승인 통과 자료"
                : "선택 단계 통과 · 다음 단계 미통과 · 보류·제외 포함"}
          </li>
          <li>상단 집계: 검색과 무관 · 원본 전체 수와 단계별 누적 통과 수 구분</li>
          <li>수집은 분석·승인을 의미하지 않음 · 역할별 권한 유지</li>
        </ul>
        <form method="get" className="search-form">
          <input type="hidden" name="stage" value={stage} />
          <label htmlFor="queue-search">
            아이디어 검색
            <input
              id="queue-search"
              type="search"
              name="q"
              placeholder="제목 또는 아이디어 ID"
              defaultValue={query}
              maxLength={200}
            />
          </label>
          <button type="submit">검색</button>
          {query && (
            <Link className="button sub" href={`/?stage=${stage}`}>
              초기화
            </Link>
          )}
        </form>
        {queue.items.length === 0 ? (
          <div className="pending">
            <b>{query ? "검색 결과 없음" : "표시할 자료 없음"}</b>
            <ul className="instructions">
              <li>{query ? "제목·아이디어 ID 또는 선택 단계 확인" : "선택 목록에 해당하는 자료 없음"}</li>
              {!isRaw && (
                <li><Link className="lnk" href="/?stage=raw">카드 생성 전 자료는 수집 원본에서 확인</Link></li>
              )}
            </ul>
            {queue.offset > 0 && (
              <Link className="lnk" href={href(stage)}>
                첫 페이지로 돌아가기
              </Link>
            )}
          </div>
        ) : (
          <ul className="queue-list">
            {queue.items.map((item) => (
              <QueueRow key={item.idea_id} item={item} />
            ))}
          </ul>
        )}
        <nav className="pagination" aria-label="목록 페이지">
          <span className="muted">
            {queue.total === 0
              ? "0건"
              : `${Math.min(queue.offset + 1, queue.total)}–${Math.min(queue.offset + queue.items.length, queue.total)} / ${queue.total.toLocaleString("ko-KR")}건`}
          </span>
          <div className="actions">
            {queue.offset > 0 ? (
              <Link
                className="button sub"
                href={href(stage, Math.max(0, queue.offset - queue.limit))}
              >
                이전
              </Link>
            ) : (
              <span className="button disabled" aria-disabled="true">
                이전
              </span>
            )}
            {queue.offset + queue.limit < queue.total ? (
              <Link
                className="button sub"
                href={href(stage, queue.offset + queue.limit)}
              >
                다음
              </Link>
            ) : (
              <span className="button disabled" aria-disabled="true">
                다음
              </span>
            )}
          </div>
        </nav>
      </section>
    </>
  );
}
