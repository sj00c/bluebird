import type { ReactNode } from "react";
import Link from "next/link";
import { CAUSE, CHANGE_KIND, VERDICT, VERDICT_PILL } from "@/lib/labels";

export function PageHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <header className="page-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <div className="page-meta">{children}</div>
    </header>
  );
}

export function Verdict({ value }: { value: string | null }) {
  return (
    <span className={`pill ${value ? (VERDICT_PILL[value] ?? "lo") : "lo"}`}>
      {value ? (VERDICT[value] ?? value) : "시의성 미평가"}
    </span>
  );
}

export function TableScroll({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <>
      <p className="table-hint muted">표 좌우 스크롤</p>
      <div
        className="table-scroll"
        role="region"
        aria-label={`${label} · 좌우 스크롤`}
        tabIndex={0}
      >
        {children}
      </div>
    </>
  );
}

export function IdeaCard({
  id,
  title,
  meta,
  cause,
  score,
  verdict,
  changeTitle,
  changeKind,
  children,
}: {
  id: string;
  title: string;
  meta: string;
  cause: string | null;
  score: number | null;
  verdict: string | null;
  changeTitle?: string | null;
  changeKind?: string | null;
  children?: ReactNode;
}) {
  const href = `/ideas/${encodeURIComponent(id)}`;
  return (
    <article className="idea-card">
      <div className="card-labels">
        <span className={`tag ${cause ? "" : "g"}`}>
          {cause ? "진단 검증 완료" : "공개 원본"}
        </span>
        <Verdict value={verdict} />
      </div>
      <h3>
        <Link href={href}>{title}</Link>
      </h3>
      <p className="muted">{meta}</p>
      <dl className="idea-facts">
        <div>
          <dt>원인 진단</dt>
          <dd>{cause ? (CAUSE[cause] ?? cause) : "검증된 진단 없음"}</dd>
        </div>
        <div>
          <dt>시의성</dt>
          <dd>
            {score != null ? (
              <>
                <strong>{Number(score).toFixed(1)}</strong> / 5.0
              </>
            ) : (
              "미채점"
            )}
          </dd>
        </div>
      </dl>
      {changeTitle && (
        <div className="change-summary">
          <span>{CHANGE_KIND[changeKind ?? ""] ?? "확인된 변화"}</span>
          <p>{changeTitle}</p>
        </div>
      )}
      {children}
      <Link className="card-link" href={href}>
        상세 보기 <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}

export function DiscoverySearch({
  id,
  query = "",
  help,
}: {
  id: string;
  query?: string;
  help?: string;
}) {
  return (
    <form action="/match" className="discovery-search">
      <label className="field-label" htmlFor={id}>
        주제·공고 검색
      </label>
      <div className="input">
        <input
          id={id}
          name="q"
          defaultValue={query}
          minLength={2}
          maxLength={200}
          required
          placeholder="주제 또는 공고 제목"
          aria-describedby={help ? `${id}-help` : undefined}
        />
        <button type="submit">
          검색 <span aria-hidden="true">↗</span>
        </button>
      </div>
      {help && (
        <p id={`${id}-help`} className="muted">
          {help}
        </p>
      )}
    </form>
  );
}
