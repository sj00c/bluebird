"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";

const KINDS = [
  ["fact", "사실 오류"],
  ["cause", "막힌 이유"],
  ["change", "바뀐 것"],
  ["privacy", "개인정보"],
  ["other", "기타"],
];

export function ObjectionForm({
  ideaId,
  initialStatus,
}: {
  ideaId: string;
  initialStatus?: string;
}) {
  const sending = useRef(false);
  const [status, setStatus] = useState(
    initialStatus === "ok"
      ? "success"
      : initialStatus === "error"
        ? "error"
        : "idle",
  );
  const [message, setMessage] = useState(
    initialStatus === "ok"
      ? "접수 완료 · 담당자 검토 대기"
      : initialStatus === "error"
        ? "접수 실패 · 입력 내용 확인 후 재시도"
        : "",
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    sending.current = true;
    setStatus("pending");
    setMessage("접수 중…");
    try {
      const response = await fetch("/api/v1/objections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idea_id: ideaId,
          kind: data.get("kind"),
          body: data.get("body"),
        }),
      });
      if (!response.ok) {
        setStatus("error");
        setMessage(
          response.status === 400
            ? "입력 오류 · 의견 종류 선택 · 공백 외 내용 필수 · 최대 2,000자"
            : response.status === 404
              ? "공개 중단 · 아이디어 풀에서 공개 상태 확인"
              : "접수 실패 · 입력 내용 유지 · 잠시 후 재시도",
        );
        return;
      }
      form.reset();
      setStatus("success");
      setMessage("접수 완료 · 담당자 검토 대기 · 접수 내용 비공개");
    } catch {
      setStatus("error");
      setMessage(
        "연결 오류 · 접수 여부 미확인 · 입력 내용 유지 · 즉시 재제출 금지",
      );
    } finally {
      sending.current = false;
    }
  }

  return (
    <form
      method="POST"
      action="/api/v1/objections"
      className="objection-form"
      onSubmit={submit}
      aria-busy={status === "pending"}
    >
      <input type="hidden" name="idea_id" value={ideaId} />
      <label htmlFor="objection-kind">의견 종류</label>
      <select
        id="objection-kind"
        name="kind"
        defaultValue="fact"
        disabled={status === "pending"}
      >
        {KINDS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <label htmlFor="objection-body">
        검증 요청 내용 <span className="muted">(필수)</span>
      </label>
      <textarea
        id="objection-body"
        name="body"
        maxLength={2000}
        required
        disabled={status === "pending"}
        aria-describedby="objection-help"
        placeholder="오류 항목 · 확인할 사실 · 참고 근거"
      />
      <ul id="objection-help" className="checklist muted">
        <li>최대 2,000자</li>
        <li>이름·연락처 등 개인정보 입력 금지</li>
        <li>열람 범위: 검토 담당자</li>
      </ul>
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className={message ? `notice ${status === "error" ? "error" : ""}` : ""}
      >
        {message}
      </div>
      <button type="submit" disabled={status === "pending"} className="btn">
        {status === "pending" ? "접수 중…" : "의견 제출"}
      </button>
    </form>
  );
}
