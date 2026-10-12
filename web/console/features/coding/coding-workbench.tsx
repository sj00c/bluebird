import type { Coding, CodingItem } from "@/lib/contracts";
import { CAUSES, cause } from "@/lib/labels";
import { code } from "@/app/actions";
import { ActionForm } from "@/app/action-form";

function CodingSample({ item, index }: { item: CodingItem; index: number }) {
  return (
    <article className="card">
      <div className="section-heading">
        <span className="eyebrow">
          표본 {String(index + 1).padStart(2, "0")}
        </span>
        <span className={`tag ${item.my_code ? "positive" : ""}`}>
          {item.my_code ? `저장됨 · ${cause(item.my_code)}` : "분류 대기"}
        </span>
      </div>
      <h2>{item.title}</h2>
      <p className="provenance mono">{item.idea_id}</p>
      <div className="coding-grid">
        <details>
          <summary>원본·문제·데이터 확인</summary>
          {item.body ? (
            <div className="body">{item.body}</div>
          ) : (
            <div className="pending">원본 본문 없음</div>
          )}
          {item.card_problem && (
            <>
              <h3>풀려던 문제</h3>
              <p>{item.card_problem}</p>
            </>
          )}
          {!!item.missing_data?.length && (
            <>
              <h3>필요했던 데이터</h3>
              <p>
                {item.missing_data.map((missing, i) => (
                  <span key={i} className="tag">
                    {typeof missing === "string" ? missing : missing.name}
                  </span>
                ))}
              </p>
            </>
          )}
        </details>
        <ActionForm action={code}>
          <input type="hidden" name="idea_id" value={item.idea_id} />
          <label>
            막힌 이유
            <select name="code" defaultValue={item.my_code ?? ""} required>
              <option value="" disabled>
                원인 선택
              </option>
              {Object.entries(CAUSES).map(([key, label]) => (
                <option key={key} value={key}>
                  {key} · {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            판단 메모 (선택)
            <textarea name="note" maxLength={1000} />
          </label>
          <div className="actions">
            <button type="submit">
              {item.my_code ? "내 코드 수정 저장" : "내 코드 저장"}
            </button>
          </div>
        </ActionForm>
      </div>
    </article>
  );
}

export function CodingWorkbench({ coding }: { coding: Coding }) {
  const completed = coding.items.filter((item) => item.my_code).length;
  return (
    <>
      <header className="page-heading">
        <div>
          <h1>독립 코딩</h1>
          <span className="muted">
            독립 분류 · 타 코더 판단·시스템 예측 비공개
          </span>
        </div>
        <span className="tag">
          내 분류 {completed} / {coding.items.length}
        </span>
      </header>
      <section className="card">
        <div className="section-heading">
          <h2>현재 표본</h2>
          <span className="muted mono">{coding.sample_id ?? "미배정"}</span>
        </div>
        <div
          className="progress-track"
          role="progressbar"
          aria-label="내 코딩 완료"
          aria-valuemin={0}
          aria-valuemax={Math.max(1, coding.items.length)}
          aria-valuenow={completed}
        >
          <span
            style={{
              width: `${coding.items.length ? (completed / coding.items.length) * 100 : 0}%`,
            }}
          />
        </div>
        <ul className="instructions">
          <li>코드: 서버 저장</li>
          <li>코더 슬롯 충돌: 저장 불가 · 오류 표시</li>
        </ul>
        {coding.items.length === 0 && (
          <div className="pending">
            <b>배정 표본 없음</b>
            <p className="hint">운영자의 표본 배정 필요</p>
          </div>
        )}
      </section>
      {coding.items.map((item, index) => (
        <CodingSample key={item.idea_id} item={item} index={index} />
      ))}
    </>
  );
}
