import { AXES, CAUSES, CHANGE_KINDS, TRACE_STATUS } from "@/lib/labels";
import type { Change, Detail } from "@/lib/contracts";
import { ActionForm } from "@/app/action-form";
import { author, review } from "@/app/actions";

function Identity({ id, kind }: { id: string; kind: string }) {
  return (
    <>
      <input type="hidden" name="idea_id" value={id} />
      <input type="hidden" name="kind" value={kind} />
    </>
  );
}
export function TraceForm({ detail: d }: { detail: Detail }) {
  const manual = d.trace?.checks.find((c) => c.item === "manual");
  const manualUrl =
    typeof manual?.detail?.url === "string" ? manual.detail.url : "";
  const manualNote =
    typeof manual?.detail?.note === "string" ? manual.detail.note : "";
  return (
    <details className="editor" open={!d.trace}>
      <summary>흔적 판정 작성·수정</summary>
      <ActionForm action={author}>
        <Identity id={d.idea.id} kind="trace" />
        <p className="hint">
          검색 후보 ≠ 실현 확인 · 직접 확인한 근거·판단 기록
        </p>
        <label>
          흔적 판정
          <select
            name="status"
            defaultValue={
              d.trace?.status &&
              d.trace.status !== "pending" &&
              d.trace.status in TRACE_STATUS
                ? d.trace.status
                : ""
            }
            required
          >
            <option value="" disabled>
              판정 선택
            </option>
            {Object.entries(TRACE_STATUS)
              .filter(([key]) => key !== "pending")
              .map(([key, value]) => (
                <option key={key} value={key}>
                  {value}
                </option>
              ))}
          </select>
        </label>
        <label>
          확인 근거 URL
          <input
            type="url"
            name="url"
            defaultValue={manualUrl}
            maxLength={2048}
            placeholder="https://…"
          />
          <small>흔적 있음 판정: 확인 가능한 원문 URL 필수</small>
        </label>
        <label>
          확인 내용 · 판단 이유
          <textarea
            name="note"
            defaultValue={manualNote}
            required
            maxLength={4000}
          />
        </label>
        <div className="actions">
          <button type="submit">흔적 판정 저장</button>
        </div>
      </ActionForm>
    </details>
  );
}
export function DiagnosisForm({ detail: d }: { detail: Detail }) {
  const evidence = d.diagnosis?.evidence ?? [];
  return (
    <details className="editor" open={!d.diagnosis}>
      <summary>원인 진단 작성·수정</summary>
      <ActionForm action={author}>
        <Identity id={d.idea.id} kind="diagnosis" />
        <div className="form-grid">
          <label>
            주된 원인
            <select
              name="cause"
              defaultValue={d.diagnosis?.cause ?? ""}
              required
            >
              <option value="" disabled>
                원인 선택
              </option>
              {Object.entries(CAUSES).map(([k, v]) => (
                <option key={k} value={k}>
                  {k} · {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            보조 원인
            <select
              name="secondary"
              defaultValue={d.diagnosis?.secondary ?? ""}
            >
              <option value="">없음</option>
              {Object.entries(CAUSES).map(([k, v]) => (
                <option key={k} value={k}>
                  {k} · {v}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          진단 이유
          <textarea
            name="rationale"
            defaultValue={d.diagnosis?.rationale ?? ""}
            required
            maxLength={4000}
          />
        </label>
        <ul className="instructions">
          <li>같은 원인: 근거 누적 보존 · 빈 URL로 기존 근거 삭제 불가</li>
          <li>주된 원인 변경: 이번 입력 근거로 재연결</li>
          <li>단계 통과: 근거 필수 · 판단 불가(U) 제외</li>
        </ul>
        {Array.from(
          { length: Math.min(30, Math.max(3, evidence.length + 1)) },
          (_, i) => (
            <div key={i} className="evidence-fields">
              <label>
                근거 {i + 1} · 원문 URL
                <input
                  type="url"
                  name="evidence_url"
                  defaultValue={evidence[i]?.url ?? ""}
                  maxLength={2048}
                  placeholder="https://…"
                />
              </label>
              <label>
                인용 내용
                <textarea
                  name="evidence_excerpt"
                  defaultValue={evidence[i]?.excerpt ?? ""}
                  maxLength={4000}
                />
              </label>
            </div>
          ),
        )}
        <div className="actions">
          <button type="submit">원인 진단 저장</button>
        </div>
      </ActionForm>
    </details>
  );
}
export function MatchForm({
  detail: d,
  changes,
}: {
  detail: Detail;
  changes: Change[];
}) {
  return (
    <>
      {d.matches.map((match) => (
        <details className="editor" key={match.id}>
          <summary>연결 수정 · {match.title}</summary>
          <MatchEditor
            id={d.idea.id}
            change={String(match.change_id)}
            match={match}
          />
        </details>
      ))}
      <details className="editor" open={d.matches.length === 0}>
        <summary>기존 변화와 새로 연결</summary>
        {changes.length === 0 ? (
          <div className="pending">
            선택 가능한 변화 없음 · 검색어 변경 또는 jobs 변화 수집 필요
          </div>
        ) : (
          <MatchEditor id={d.idea.id} changes={changes} />
        )}
      </details>
    </>
  );
}
function MatchEditor({
  id,
  change,
  changes,
  match,
}: {
  id: string;
  change?: string;
  changes?: Change[];
  match?: Detail["matches"][number];
}) {
  return (
    <ActionForm action={author}>
      <Identity id={id} kind="match" />
      {change ? (
        <input type="hidden" name="change_id" value={change} />
      ) : (
        <label>
          연결할 변화
          <select name="change_id" defaultValue="" required>
            <option value="" disabled>
              수집된 변화 선택
            </option>
            {changes?.map((c) => (
              <option key={c.id} value={c.id}>
                {CHANGE_KINDS[c.kind] ?? c.kind} · {c.title} (
                {c.verify_status ?? "미확인"})
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        연결 판정
        <select name="verdict" defaultValue={match?.llm_verdict ?? ""} required>
          <option value="" disabled>
            판정 선택
          </option>
          <option value="yes">연결됨</option>
          <option value="partial">부분 연결</option>
          <option value="no">연결 안 됨</option>
          <option value="human">담당자가 근거를 확인한 연결</option>
        </select>
      </label>
      <label>
        변화 항목
        <textarea
          name="what_changed"
          defaultValue={match?.what_changed.join("\n") ?? ""}
          required
          maxLength={8000}
        />
        <small>한 줄에 한 항목 · 최대 20개 · 항목당 4,000자</small>
      </label>
      <label>
        현재 가능한 조건
        <textarea
          name="how_now"
          defaultValue={match?.how_now ?? ""}
          required
          maxLength={4000}
        />
      </label>
      <div className="actions">
        <button type="submit">변화 연결 저장</button>
      </div>
    </ActionForm>
  );
}
export function ScoreForm({ detail: d }: { detail: Detail }) {
  return (
    <details className="editor" open={!d.timeliness}>
      <summary>시의성 점수 작성·수정</summary>
      <ActionForm action={author}>
        <Identity id={d.idea.id} kind="score" />
        <ul className="instructions">
          <li>축별 0–5점 · 원문 근거 URL 기록</li>
          <li>알 수 없는 축: 미평가</li>
          <li>합계·판정: 서버 계산</li>
        </ul>
        <label>
          평가 기준일
          <input
            type="date"
            name="as_of"
            defaultValue={
              d.timeliness?.as_of ?? new Date().toISOString().slice(0, 10)
            }
            required
          />
        </label>
        {Object.entries(AXES).map(([axis, label]) => {
          const key = axis as keyof typeof AXES;
          return (
            <div className="score-fields" key={axis}>
              <label>
                {label} 점수
                <select name={axis} defaultValue={d.timeliness?.[key] ?? ""}>
                  <option value="">미평가</option>
                  {[0, 1, 2, 3, 4, 5].map((n) => (
                    <option value={n} key={n}>
                      {n}점
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {label} 근거 URL
                <input
                  type="url"
                  name={`${axis}_evidence`}
                  defaultValue={d.timeliness?.evidence?.[key] ?? ""}
                  maxLength={2048}
                  placeholder="https://…"
                />
              </label>
            </div>
          );
        })}
        <div className="actions">
          <button type="submit">시의성 평가 저장</button>
        </div>
      </ActionForm>
    </details>
  );
}
export function ReviewForm({
  id,
  round,
  decision,
  label,
}: {
  id: string;
  round: string;
  decision: string;
  label: string;
}) {
  return (
    <ActionForm action={review}>
      <input type="hidden" name="idea_id" value={id} />
      <input type="hidden" name="round" value={round} />
      <input type="hidden" name="decision" value={decision} />
      <label>
        {decision === "reject" ? "반려 사유 (필수)" : "검토 메모 (선택)"}
        <textarea
          name="note"
          required={decision === "reject"}
          maxLength={2000}
        />
      </label>
      <div className="actions">
        <button
          type="submit"
          className={decision === "reject" ? "danger" : undefined}
        >
          {label}
        </button>
      </div>
    </ActionForm>
  );
}
