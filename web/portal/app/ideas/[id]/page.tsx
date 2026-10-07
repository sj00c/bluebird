import Link from "next/link";
import { notFound } from "next/navigation";
import { getIdea, getRevival } from "@/lib/db";

export const dynamic = "force-dynamic";

const CAUSE: Record<string, string> = {
  T: "기술 미성숙",
  D: "데이터 부족",
  R: "규제",
  M: "시장·수요",
  C: "사업화 역량·자금",
  O: "기타",
  U: "판단 불가",
};
const CHANGE_KIND: Record<string, string> = {
  dataset_opened: "데이터 개방",
  law_effective: "법령 시행",
  announcement: "지원 공고",
  policy_news: "정책",
  tech: "기술",
};
const VERDICT: Record<string, string> = { now: "지금 가능", conditional: "조건부 가능" };
const OBJECTION_KIND: [string, string][] = [
  ["fact", "사실 오류"],
  ["cause", "막힌 이유"],
  ["change", "바뀐 것"],
  ["privacy", "개인정보"],
  ["other", "기타"],
];

export default async function IdeaPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ objection?: string }>;
}) {
  const { id } = await params;
  const { objection } = await searchParams;
  const idea = await getIdea(id);
  if (!idea) notFound();
  const { diagnosis, changes, timeliness, evidence } = await getRevival(id);
  const evById = new Map(evidence.map((e) => [e.id, e]));
  const axes: [string, number | null][] = timeliness
    ? [
        ["기술", timeliness.tech],
        ["데이터", timeliness.data],
        ["규제", timeliness.regulation],
        ["정책", timeliness.policy],
      ]
    : [];
  const evidenceBlock = (ids: string[]) =>
    ids.map((eid) => {
      const e = evById.get(eid);
      if (!e) return null;
      return (
        <div key={eid}>
          {e.url ? (
            <a href={e.url} target="_blank" rel="noopener noreferrer">{e.title || e.url}</a>
          ) : (
            <span>{e.title}</span>
          )}
          {e.excerpt && <div className="quote">{e.excerpt}</div>}
        </div>
      );
    });

  return (
    <div className="card">
      <p className="muted">
        <Link href="/pool">아이디어 풀</Link> › {idea.id}
      </p>
      <h1>{idea.title}</h1>
      <div>
        {idea.category && <span className="tag">분류: {idea.category}</span>}
        <span className="tag">
          제출 {idea.year ?? "-"} · {idea.contest_name}
          {idea.award && ` · ${idea.award}`}
        </span>
        {idea.host_org && <span className="tag">주최: {idea.host_org}</span>}
      </div>
      {idea.body && <div className="body">{idea.body}</div>}
      {idea.used_data.length > 0 && (
        <>
          <h2>당시 활용 데이터</h2>
          {idea.used_data.map((d) => <span key={d} className="tag">{d}</span>)}
        </>
      )}
      <h2>사업화 흔적 · 정체 원인 · 시의성</h2>
      {diagnosis ? (
        <>
          <div className="step">
            <h3>1 원본</h3>
            <p>위에 보이는 제출 당시의 아이디어입니다.</p>
          </div>
          <div className="step">
            <h3>2 막힌 이유</h3>
            <p>
              <span className="tag">{diagnosis.cause} {CAUSE[diagnosis.cause] ?? diagnosis.cause}</span>
              {diagnosis.secondary && (
                <span className="tag">보조 {diagnosis.secondary} {CAUSE[diagnosis.secondary] ?? diagnosis.secondary}</span>
              )}
            </p>
            {diagnosis.rationale && <p>{diagnosis.rationale}</p>}
            {evidenceBlock(diagnosis.evidence_ids)}
          </div>
          <div className="step">
            <h3>3 바뀐 것</h3>
            {changes.length === 0 && <p className="muted">확인된 변화가 없습니다.</p>}
            {changes.map((c) => (
              <div key={c.id} style={{ marginBottom: 10 }}>
                <p>
                  <span className="tag">{CHANGE_KIND[c.kind] ?? c.kind}</span>
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noopener noreferrer"><strong>{c.title}</strong></a>
                  ) : (
                    <strong>{c.title}</strong>
                  )}
                </p>
                {c.occurred_at && <p className="muted">시행/발생 {c.occurred_at}</p>}
                {c.what_changed.length > 0 && (
                  <ul>{c.what_changed.map((w, i) => <li key={i}>{w}</li>)}</ul>
                )}
                {c.how_now && <p>{c.how_now}</p>}
                {evidenceBlock(c.evidence_ids)}
              </div>
            ))}
          </div>
          <div className="step">
            <h3>4 지금 하려면</h3>
            {timeliness ? (
              <>
                <p>
                  <span className="verdict">{VERDICT[timeliness.verdict] ?? timeliness.verdict}</span>
                  {timeliness.s != null && <span>S {Number(timeliness.s).toFixed(1)}</span>}
                </p>
                <p>
                  {axes.filter(([, v]) => v != null).map(([k, v]) => (
                    <span key={k} className="tag">{k} {v}</span>
                  ))}
                </p>
                {timeliness.resolve_condition && <p>{timeliness.resolve_condition}</p>}
                {timeliness.as_of && <p className="muted">기준일 {timeliness.as_of}</p>}
              </>
            ) : (
              <p className="muted">아직 시의성 평가가 없습니다.</p>
            )}
          </div>
        </>
      ) : (
        <div className="pending">담당자 검증을 마친 진단만 공개합니다. 이 아이디어는 아직 검증 대기 상태입니다.</div>
      )}
      <h2 id="objection">이의 제기</h2>
      <p className="muted">사실이 틀렸거나 개인정보가 보이면 알려 주세요. 담당자가 확인한 뒤 반영합니다.</p>
      {objection === "ok" && <div className="notice">의견을 받았습니다. 감사합니다.</div>}
      {objection === "error" && (
        <div className="notice error">제출하지 못했습니다. 내용을 확인하고 다시 시도해 주세요.</div>
      )}
      <form method="POST" action="/api/v1/objections" className="objection-form">
        <input type="hidden" name="idea_id" value={idea.id} />
        <select name="kind" defaultValue="fact" aria-label="종류">
          {OBJECTION_KIND.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <textarea name="body" maxLength={2000} required aria-label="내용" placeholder="어떤 점이 틀렸는지 적어 주세요." />
        <button type="submit">제출</button>
      </form>
      <h2>출처</h2>
      <p className="muted">
        {idea.source_name} ({idea.license})
        {idea.source_url && (
          <>
            {" · "}
            <a href={idea.source_url} target="_blank" rel="noopener noreferrer">원문 링크</a>
          </>
        )}
      </p>
    </div>
  );
}
