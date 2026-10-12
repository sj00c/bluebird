"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { CAUSE } from "@/lib/labels";
import { Verdict } from "./components";

export type WorkspaceRecord = {
  id: string;
  title: string;
  year: number | null;
  source_name: string;
  contest_name: string;
  award: string | null;
  cause: string | null;
  verdict: string | null;
  s: number | null;
};

export function RecordWorkbench({
  records,
  total,
}: {
  records: WorkspaceRecord[];
  total: number;
}) {
  const [selectedId, setSelectedId] = useState(records[0]?.id);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = Math.max(
    0,
    records.findIndex((record) => record.id === selectedId),
  );
  const selected = records[selectedIndex];

  function moveSelection(
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    let next: number;
    switch (event.key) {
      case "ArrowDown":
        next = (index + 1) % records.length;
        break;
      case "ArrowUp":
        next = (index - 1 + records.length) % records.length;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = records.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    tabs.current[next]?.focus();
  }

  return (
    <section className="record-workbench" aria-labelledby="records-title">
      <div className="record-canvas">
        <div className="canvas-heading">
          <div>
            <p className="eyebrow">01 / 공개 원본</p>
            <h2 id="records-title">
              아이디어 탐색{" "}
              <span>{records.length.toString().padStart(2, "0")}</span>
            </h2>
          </div>
          <span className="muted">제출 연도 최신순</span>
        </div>
        {selected ? (
          <>
            <p id="record-selection-help" className="sr-only">
              아이디어를 선택하면 오른쪽 또는 아래에 상세 정보가 표시됩니다.
              위아래 방향키로 선택하고 Home, End 키로 처음과 마지막 항목으로
              이동합니다.
            </p>
            <div
              className="record-tabs"
              role="tablist"
              aria-label="공개 아이디어 선택"
              aria-orientation="vertical"
              aria-describedby="record-selection-help"
            >
              {records.map((record, index) => (
                <button
                  key={record.id}
                  ref={(element) => {
                    tabs.current[index] = element;
                  }}
                  type="button"
                  role="tab"
                  id={`record-tab-${index}`}
                  aria-selected={index === selectedIndex}
                  aria-controls="record-inspector"
                  tabIndex={index === selectedIndex ? 0 : -1}
                  className="record-tab"
                  onClick={() => setSelectedId(record.id)}
                  onFocus={() => setSelectedId(record.id)}
                  onKeyDown={(event) => moveSelection(event, index)}
                >
                  <span className="record-index" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="record-title-group">
                    <span className="record-meta">
                      {record.year ?? "연도 미상"} · {record.source_name}
                    </span>
                    <span className="record-title">{record.title}</span>
                  </span>
                  <span className="record-selection-mark" aria-hidden="true">
                    {index === selectedIndex ? "↗" : "+"}
                  </span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="pending">
            <strong>공개 아이디어 없음</strong>
            <p>공개된 원본이 등록되면 이곳에 표시됩니다.</p>
          </div>
        )}
        <Link className="record-more" href="/pool">
          전체 {total.toLocaleString("ko-KR")}건 조회{" "}
          <span aria-hidden="true">→</span>
        </Link>
      </div>
      {selected ? (
        <aside
          className="record-inspector"
          id="record-inspector"
          role="tabpanel"
          aria-labelledby={`record-tab-${selectedIndex}`}
          tabIndex={0}
        >
          <div className="inspector-heading">
            <p className="eyebrow">02 / 선택한 기록</p>
            <span className="inspector-position">
              {String(selectedIndex + 1).padStart(2, "0")} /{" "}
              {String(records.length).padStart(2, "0")}
            </span>
          </div>
          <div
            aria-live="polite"
            aria-atomic="true"
            className="inspector-content"
          >
            <h3>{selected.title}</h3>
            <div className="inspector-status">
              <span className={`tag ${selected.cause ? "" : "g"}`}>
                {selected.cause ? "진단 검증 완료" : "공개 원본"}
              </span>
              <Verdict value={selected.verdict} />
            </div>
            <dl className="record-facts">
              <div>
                <dt>제출 연도</dt>
                <dd>{selected.year ?? "연도 미상"}</dd>
              </div>
              <div>
                <dt>출처</dt>
                <dd>{selected.source_name}</dd>
              </div>
              <div>
                <dt>공모전</dt>
                <dd>{selected.contest_name || "기록 없음"}</dd>
              </div>
              <div>
                <dt>수상</dt>
                <dd>{selected.award || "기록 없음"}</dd>
              </div>
              <div>
                <dt>원인 진단</dt>
                <dd>
                  {selected.cause
                    ? (CAUSE[selected.cause] ?? selected.cause)
                    : "검증된 진단 없음"}
                </dd>
              </div>
              <div>
                <dt>시의성</dt>
                <dd>
                  {selected.s != null
                    ? `${Number(selected.s).toFixed(1)} / 5.0`
                    : "미채점"}
                </dd>
              </div>
            </dl>
          </div>
          <Link
            className="btn inspector-open"
            href={`/ideas/${encodeURIComponent(selected.id)}`}
          >
            원본·검증 근거 열기 <span aria-hidden="true">↗</span>
          </Link>
        </aside>
      ) : (
        <aside className="record-inspector">
          <p className="eyebrow">02 / 선택한 기록</p>
          <p className="muted">선택할 공개 기록 없음</p>
        </aside>
      )}
    </section>
  );
}
