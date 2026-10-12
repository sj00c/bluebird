import Link from "next/link";
import type { Objection } from "@/lib/contracts";
import { OBJECTION_KINDS, OBJECTION_STATUS, when } from "@/lib/labels";
import { resolveObjection } from "@/app/actions";
import { ActionForm } from "@/app/action-form";

function ObjectionRecord({
  objection: o,
  canResolve,
}: {
  objection: Objection;
  canResolve: boolean;
}) {
  return (
    <article className="objection-item">
      <div className="section-heading">
        <span className="eyebrow">접수 #{o.id}</span>
        <span className="tag">{OBJECTION_STATUS[o.status] ?? o.status}</span>
      </div>
      <h2>
        <Link className="lnk" href={`/ideas/${encodeURIComponent(o.idea_id)}`}>
          {o.title ?? o.idea_id} →
        </Link>
      </h2>
      <p>
        <span className="tag">{OBJECTION_KINDS[o.kind] ?? o.kind}</span>
        <span className="muted">
          접수 {when(o.submitted_at)} · 가져옴 {when(o.pulled_at)}
        </span>
      </p>
      <details>
        <summary>접수 원문</summary>
        <div className="body">{o.body}</div>
      </details>
      {o.status !== "open" ? (
        <div className="resolution">
          <details>
            <summary>처리 기록</summary>
            <p className="prewrap">{o.resolution ?? "처리 내용 미기록"}</p>
          </details>
          <p className="muted">
            {when(o.resolved_at)} · {o.resolved_by ?? "담당자 미기록"}
          </p>
        </div>
      ) : canResolve ? (
        <details className="editor" open>
          <summary>처리 결정 작성</summary>
          <ActionForm action={resolveObjection}>
            <input type="hidden" name="objection_id" value={String(o.id)} />
            <label>
              결정
              <select name="decision" defaultValue="" required>
                <option value="" disabled>
                  처리 결정 선택
                </option>
                <option value="accepted">수용 · 분석 공개 승인 철회</option>
                <option value="rejected">기각 · 기존 판단 유지</option>
              </select>
            </label>
            <label>
              처리 내용 (필수)
              <textarea name="resolution" required maxLength={2000} />
              <small>공개 가능 · 개인정보 입력 금지</small>
            </label>
            <label className="check">
              <input type="checkbox" name="withhold" />
              원본까지 공개 중단 (개인정보 등, 수용 시 적용)
            </label>
            <div className="actions">
              <button type="submit">처리 결정 저장</button>
            </div>
          </ActionForm>
        </details>
      ) : (
        <p className="hint">검토자 처리 대기</p>
      )}
    </article>
  );
}

export function ObjectionWorkbench({
  items,
  status,
  canResolve,
}: {
  items: Objection[];
  status: string;
  canResolve: boolean;
}) {
  return (
    <>
      <header className="page-heading">
        <div>
          <h1>이의 관리</h1>
        </div>
        <span className="tag">
          {canResolve ? "검토자 · 처리 가능" : "감사자 · 읽기 전용"}
        </span>
      </header>
      <section className="card">
        <nav className="pills" aria-label="이의 처리 상태">
          {Object.entries(OBJECTION_STATUS).map(([key, label]) => (
            <Link
              key={key}
              href={`/objections?status=${key}`}
              className={key === status ? "on" : ""}
              aria-current={key === status ? "page" : undefined}
            >
              {label}
            </Link>
          ))}
        </nav>
        <ul className="instructions">
          <li>접수 표시: jobs 가져오기 배치 후</li>
          <li>수용에 따른 공개 변경: 다음 공개 배치 반영</li>
        </ul>
        {!canResolve && (
          <div className="msg info">
            감사 권한: 열람 전용 · 처리 권한: 검토자
          </div>
        )}
        {items.length === 0 && (
          <div className="pending">
            <b>{OBJECTION_STATUS[status]} 이의 없음</b>
            <p className="hint">상태 변경 또는 접수함 가져오기 후 확인</p>
          </div>
        )}
        {items.map((item) => (
          <ObjectionRecord
            key={item.id}
            objection={item}
            canResolve={canResolve}
          />
        ))}
      </section>
    </>
  );
}
