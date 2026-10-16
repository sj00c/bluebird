import Link from "next/link";
import type { Changes, Detail, Me } from "@/lib/contracts";
import { STAGES, STAGE_NAMES } from "@/lib/labels";
import { EvidenceSections } from "./evidence-sections";
import { ChangeSection } from "./change-section";
import { ScoreSection } from "./score-section";
import { ApprovalSection } from "./approval-section";
import { ReviewHistory } from "./review-history";

export function IdeaWorkspace({
  detail: d,
  me,
  canAuthor,
  changeQuery,
  changes,
}: {
  detail: Detail;
  me: Me;
  canAuthor: boolean;
  changeQuery: string;
  changes: Changes;
}) {
  const { idea } = d;
  const current = [...STAGES].reverse().find((s) => d.stage[s]);
  const next = idea.withheld_at
    ? "원본 공개 중단 · 승인 불가"
    : !canAuthor
      ? "역할별 검토 기록"
      : current === "s5"
        ? "승인 완료 · 분석 수정 시 재승인"
        : current
          ? STAGE_NAMES[STAGES[STAGES.indexOf(current) + 1]]
          : "수집 원본 확인 · 카드 미생성";
  const nextAnchor = idea.withheld_at
    ? "history"
    : !canAuthor
      ? "approval"
      : !current
        ? "original"
        : (
            {
              s0: "trace",
              s1: "diagnosis",
              s2: "changes",
              s3: "score",
              s4: "approval",
              s5: "approval",
            } as Record<string, string>
          )[current];
  return (
    <>
      <p className="breadcrumb">
        <Link href="/">검토 대기열</Link>
        <span>/</span>
        <span className="mono">{idea.id}</span>
      </p>
      <div className="page-heading">
        <div>
          <p className="eyebrow">아이디어 검토</p>
          <h1>{idea.title}</h1>
          <p className="muted">
            {idea.year ?? "연도 미상"} · {idea.contest ?? idea.source_id}
            {idea.award ? ` · ${idea.award}` : ""}
          </p>
        </div>
        <span className={`tag ${idea.withheld_at ? "warning" : ""}`}>
          {idea.withheld_at
            ? "원본 공개 중단"
            : d.stage.s5
              ? "최종 승인"
              : !d.card
                ? "수집 원본 · 카드 미생성"
                : "분석 검토 중"}
        </span>
      </div>
      <div className="next-action">
        <div>
          <small>다음 작업</small>
          <b>{next}</b>
        </div>
        <a className="button sub" href={`#${nextAnchor}`}>
          해당 영역으로 이동 ↓
        </a>
      </div>
      <ol className="workflow-stages" aria-label="단계별 통과 상태">
        {STAGES.map((s) => (
          <li key={s} className={d.stage[s] ? "done" : ""}>
            <small>{s.toUpperCase()}</small>
            <b>{STAGE_NAMES[s]}</b>
            <span>{d.stage[s] ? "통과" : "미통과"}</span>
          </li>
        ))}
      </ol>
      <nav className="section-nav" aria-label="작업 공간 목차">
        {[
          ["original", "원본·카드"],
          ["trace", "흔적"],
          ["diagnosis", "원인"],
          ["changes", "변화"],
          ["score", "시의성"],
          ["approval", "승인"],
          ["history", "기록"],
        ].map(([anchor, label]) => (
          <a key={anchor} href={`#${anchor}`}>
            {label}
          </a>
        ))}
      </nav>
      <ul className="instructions">
        <li>
          {canAuthor ? "검토자 작성 모드" : "근거 열람 모드"} · 분석 수정 시
          기존 공개 승인 철회 가능
        </li>
        <li>저장 → 재검토·승인</li>
      </ul>
      <div className="workspace-grid">
        <div>
          <EvidenceSections detail={d} canAuthor={canAuthor} />
          <ChangeSection
            detail={d}
            canAuthor={canAuthor}
            changeQuery={changeQuery}
            changes={changes}
          />
          <ScoreSection detail={d} canAuthor={canAuthor} />
        </div>
        <aside className="workspace-aside">
          <ApprovalSection detail={d} me={me} />
        </aside>
      </div>
      <ReviewHistory detail={d} />
    </>
  );
}
