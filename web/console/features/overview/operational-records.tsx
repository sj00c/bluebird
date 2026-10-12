import type { Overview } from "@/lib/contracts";
import { STAGE_NAMES, when } from "@/lib/labels";

const statusName: Record<string, string> = {
  ok: "정상",
  success: "완료",
  succeeded: "완료",
  running: "실행 중",
  failed: "실패",
  error: "오류",
  skipped: "건너뜀",
  blocked: "차단",
  ready: "준비",
  missing_key: "인증 키 필요",
  key_required: "인증 키 필요",
};

export function OperationalRecords({ overview: d }: { overview: Overview }) {
  return (
    <>
      <section className="card" id="connections">
        <div className="section-heading">
          <h2>외부 연결 점검</h2>
          <span className="tag">실제 점검 기록</span>
        </div>
        <ul className="instructions">
          <li>출처별 마지막 점검 · 목록에 없는 연결: 미점검</li>
          <li>인증 키·수집 실행: jobs 운영 설정</li>
        </ul>
        {d.checks.length === 0 ? (
          <div className="pending">외부 연결 점검 기록 없음</div>
        ) : (
          <ul className="connection-list">
            {d.checks.map((check) => (
              <li key={check.source_id}>
                <div>
                  <strong>
                    {d.sources.find((source) => source.id === check.source_id)
                      ?.name ?? check.source_id}
                  </strong>
                  <p className="muted">{check.source_id}</p>
                </div>
                <span
                  className={`tag ${check.status === "ok" ? "positive" : "warning"}`}
                >
                  {statusName[check.status] ?? check.status}
                </span>
                <time className="muted" dateTime={check.checked_at}>
                  {when(check.checked_at)}
                </time>
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="overview-grid">
        <section className="card">
          <div className="section-heading">
            <h2>출처와 공개 정책</h2>
            <span className="tag">{d.sources.length}개 출처</span>
          </div>
          <p className="hint">원본 공개 허용 ≠ 개별 분석 검토·승인</p>
          {d.sources.length === 0 ? (
            <div className="pending">등록 출처 없음</div>
          ) : (
            <ul className="source-list">
              {d.sources.map((source) => (
                <li key={source.id}>
                  <div className="section-heading">
                    <h3>{source.name}</h3>
                    <span className="tag">
                      원본 {source.public_ok ? "공개 허용" : "비공개"}
                    </span>
                  </div>
                  <p className="muted">
                    {source.id} · 아이디어{" "}
                    {source.ideas.toLocaleString("ko-KR")}건 · 등급{" "}
                    {source.export_grade ?? "미설정"}
                  </p>
                  <p className="hint">
                    연결{" "}
                    {source.check_status
                      ? (statusName[source.check_status] ?? source.check_status)
                      : "미점검"}{" "}
                    · {when(source.checked_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card">
          <h2>최근 작업 실행</h2>
          <ul className="instructions">
            <li>최근 최대 20회 · 과거 실패 ≠ 현재 연결 상태</li>
            <li>외부 수집·공개 실행: jobs</li>
          </ul>
          {d.runs.length === 0 ? (
            <div className="pending">작업 실행 기록 없음</div>
          ) : (
            <ol className="run-list">
              {d.runs.map((run, index) => (
                <li key={`${run.stage}-${run.started_at}-${index}`}>
                  <div className="section-heading">
                    <strong>{STAGE_NAMES[run.stage] ?? run.stage}</strong>
                    <span
                      className={`tag ${["failed", "error", "blocked"].includes(run.status) ? "warning" : ""}`}
                    >
                      {statusName[run.status] ?? run.status}
                    </span>
                  </div>
                  <p className="muted">
                    시작 {when(run.started_at)}
                    <br />
                    종료 {run.finished_at ? when(run.finished_at) : "미기록"}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </>
  );
}
