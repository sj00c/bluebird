import Link from "next/link";
import type { Me, Overview } from "@/lib/contracts";
import { STAGES, STAGE_NAMES } from "@/lib/labels";
import { OperationalRecords } from "./operational-records";

const workLabels: Record<string, string> = {
  s0: "실현 흔적 확인",
  s1: "막힌 원인 진단",
  s2: "달라진 조건 연결",
  s3: "시의성 평가",
  s4: "최종 승인 검토",
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
  const authorWork = [...transitions].reverse();
  const priority = authorWork.find((item) => item.remaining > 0);
  const canAuthor = me.roles.includes("reviewer");
  const connections = d.checks.filter((check) => check.status !== "ok");
  const unchecked = d.sources.filter((source) => !source.check_status).length;

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
                      : "최종 승인 목록"}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
          <ul className="instructions">
            <li>누적 수 합산 불가 · 단계 선택: 다음 단계 미통과 목록</li>
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
                : "승인 완료 확인"}
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
                <Link className="button" href="/?stage=s5">
                  승인 완료 목록 →
                </Link>
              </>
            )}
            <ul className="instructions">
              <li>승인에 가까운 단계 우선 · 보류·제외 조건 포함</li>
            </ul>
          </section>

          <aside className="operations-brief" aria-label="연결 및 승인 상태">
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
                <h2>최종 승인</h2>
              </div>
              <p className="publication-count">
                <strong>{(d.counts.s5 ?? 0).toLocaleString("ko-KR")}</strong>건
                현재 승인 통과
              </p>
              <ul className="instructions">
                <li>분석 수정 시 승인 철회 · 재승인 필요</li>
              </ul>
              <Link className="lnk" href="/?stage=s5">
                승인된 분석 보기 →
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
