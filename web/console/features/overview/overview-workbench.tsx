import Link from "next/link";
import type { Me, Overview } from "@/lib/contracts";
import { STAGES, STAGE_NAMES, when } from "@/lib/labels";
import { OperationalRecords } from "./operational-records";

const workLabels: Record<string, string> = {
  s0: "실현 흔적 확인",
  s1: "막힌 원인 진단",
  s2: "달라진 조건 연결",
  s3: "시의성 평가",
  s4: "최종 승인 검토",
  s5: "공개 조건·배치 확인",
};

export function OverviewWorkbench({
  overview: d,
  me,
}: {
  overview: Overview;
  me: Me;
}) {
  const transitions = STAGES.slice(0, -1).map((stage, index) => ({
    stage,
    // The funnel is cumulative: each later stage requires all earlier stages.
    remaining: (d.counts[stage] ?? 0) - (d.counts[STAGES[index + 1]] ?? 0),
  }));
  const authorWork = transitions.slice(0, -1).reverse();
  const priority = authorWork.find((item) => item.remaining > 0);
  const canAuthor = me.roles.includes("reviewer");
  const connections = d.checks.filter((check) => check.status !== "ok");
  const unchecked = d.sources.filter((source) => !source.check_status).length;
  const publish = d.latest_publish;
  const awaitingPublish =
    transitions.find((item) => item.stage === "s5")?.remaining ?? 0;

  return (
    <>
      <header className="page-heading">
        <div>
          <h1>운영 개요</h1>
        </div>
        <Link href="/" className="button sub">
          전체 대기열
        </Link>
      </header>

      <div className="overview-workbench">
        <section
          className="stage-flow-section overview-workplane"
          aria-labelledby="flow-title"
        >
          <div className="section-heading">
            <h2 id="flow-title">단계별 현황</h2>
            <span className="muted">단계별 누적 통과</span>
          </div>
          <p className="publication-count">
            <Link className="lnk" href="/?stage=raw">수집 원본</Link>{" "}
            <strong>{(d.counts.raw ?? 0).toLocaleString("ko-KR")}</strong>건
          </p>
          <ul className="instructions">
            <li>공개 중단 자료 제외 · 카드·분석 생성 여부와 무관</li>
            <li>아래 단계별 통과 수와 별도 집계 · 수집 ≠ 분석·승인</li>
          </ul>
          <ol className="stage-flow">
            {STAGES.map((stage, index) => (
              <li key={stage}>
                <Link href={`/?stage=${stage}`}>
                  <span className="flow-step">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span>{STAGE_NAMES[stage]}</span>
                  <strong>
                    {(d.counts[stage] ?? 0).toLocaleString("ko-KR")}
                    <small>건</small>
                  </strong>
                  <span className="flow-caption">
                    {index < transitions.length
                      ? `다음 단계 미통과 ${transitions[index].remaining.toLocaleString("ko-KR")}`
                      : "공개 반영 목록"}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
          <ul className="instructions">
            <li>누적 수 합산 불가 · 단계 선택: 다음 단계 미통과 목록</li>
            <li>저장·승인 ≠ 즉시 공개 · 별도 공개 배치 필요</li>
          </ul>
        </section>
        <div className="workbench-lead">
          <section className="priority-panel" aria-labelledby="priority-title">
            <p className="eyebrow">우선 대기열</p>
            <h2 id="priority-title">
              {priority
                ? canAuthor
                  ? workLabels[priority.stage]
                  : "역할별 검토"
                : awaitingPublish > 0
                  ? "공개 조건 확인"
                  : "공개 상태 확인"}
            </h2>
            {priority ? (
              <>
                <p className="priority-count">
                  <strong>{priority.remaining.toLocaleString("ko-KR")}</strong>
                  건
                </p>
                <ul className="instructions">
                  <li>{STAGE_NAMES[priority.stage]} 통과 · 다음 단계 미통과</li>
                  <li>
                    {canAuthor
                      ? "분석 작성·최종 승인 권한"
                      : "전문가·감사 검토 권한 · 작성·최종 승인: 검토자"}
                  </li>
                </ul>
                <Link className="button" href={`/?stage=${priority.stage}`}>
                  {canAuthor ? "다음 작업 확인" : "내 역할로 검토하기"} →
                </Link>
              </>
            ) : (
              <>
                <ul className="instructions">
                  <li>작성·승인 단계 잔여 없음</li>
                  <li><Link className="lnk" href="/?stage=raw">카드 생성 전 자료는 수집 원본에서 확인</Link></li>
                </ul>
                <Link
                  className="button"
                  href={awaitingPublish > 0 ? "/?stage=s5" : "/?stage=s6"}
                >
                  {awaitingPublish > 0 ? "공개 조건 확인" : "공개 반영 목록"} →
                </Link>
              </>
            )}
            <ul className="instructions">
              <li>공개에 가까운 단계 우선 · 보류·제외 조건 포함</li>
            </ul>
          </section>

          <aside className="operations-brief" aria-label="연결 및 공개 상태">
            <section>
              <div className="section-heading">
                <h2>연결 확인</h2>
                <span className={`tag ${connections.length ? "warning" : ""}`}>
                  {connections.length}건 확인 필요
                </span>
              </div>
              <ul className="instructions">
                <li>
                  {connections.length
                    ? "비정상 결과: 인증·차단 사유 확인"
                    : "기록된 비정상 결과 없음"}
                </li>
                <li>미점검 출처 {unchecked}개 · 정상 여부 미확인</li>
              </ul>
              <a className="lnk" href="#connections">
                점검 결과 보기 →
              </a>
            </section>
            <section>
              <div className="section-heading">
                <h2>공개 반영</h2>
                <span className="tag">별도 배치</span>
              </div>
              <p className="publication-count">
                <strong>{(d.counts.s6 ?? 0).toLocaleString("ko-KR")}</strong>건
                현재 공개 반영 통과
              </p>
              <ul className="instructions">
                <li>
                  승인 후 공개 미통과 {awaitingPublish.toLocaleString("ko-KR")}
                  건
                </li>
                <li>출처 공개 정책 등 추가 조건 확인</li>
              </ul>
              <dl className="publish-facts">
                <div>
                  <dt>최근 스냅샷</dt>
                  <dd>
                    {publish
                      ? `#${publish.id} · ${publish.applied_at ? "반영 완료" : "반영 대기"}`
                      : "기록 없음"}
                  </dd>
                </div>
                {publish && (
                  <>
                    <div>
                      <dt>생성</dt>
                      <dd>{when(publish.created_at)}</dd>
                    </div>
                    <div>
                      <dt>공개 DB 반영</dt>
                      <dd>{when(publish.applied_at)}</dd>
                    </div>
                  </>
                )}
              </dl>
              <Link className="lnk" href="/?stage=s6">
                반영된 분석 보기 →
              </Link>
            </section>
          </aside>
        </div>
        <div className="overview-records">
          <OperationalRecords overview={d} />
        </div>
      </div>
    </>
  );
}
