import Link from "next/link";
import { notFound } from "next/navigation";
import { announcementMatches, getIdea, getRevival, similarCount, type EvidenceRow } from "@/lib/db";
import { AXES, CAUSE, CHANGE_KIND, TRACE, TRACE_ITEMS, tierText, traceText, VERDICT, VERDICT_PILL } from "@/lib/labels";

export const dynamic = "force-dynamic";

const OBJECTION_KIND: [string, string][] = [
  ["fact", "사실 오류"],
  ["cause", "막힌 이유"],
  ["change", "바뀐 것"],
  ["privacy", "개인정보"],
  ["other", "기타"],
];

function Evidence({ ids, byId }: { ids: string[]; byId: Map<string, EvidenceRow> }) {
  return (
    <>
      {ids.map((eid) => {
        const e = byId.get(eid);
        if (!e) return null;
        return (
          <div key={eid}>
            {e.url ? (
              <a className="link" href={e.url} target="_blank" rel="noopener noreferrer">{e.title || e.url}</a>
            ) : (
              <span>{e.title}</span>
            )}
            {e.excerpt && <div className="quote">{e.excerpt}</div>}
          </div>
        );
      })}
    </>
  );
}

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
  const [{ diagnosis, changes, timeliness, evidence }, similar, matches] = await Promise.all([
    getRevival(id),
    similarCount(id, idea.title),
    announcementMatches(id),
  ]);
  const byId = new Map(evidence.map((e) => [e.id, e]));
  const searched = idea.external_search === "done";
  const traced = idea.trace_status && idea.trace_status !== "pending";

  return (
    <>
      <div className="cols-a">
        {/* 왼쪽: 아이디어·사업화 흔적·정체 원인 */}
        <div className="card">
          <div className="crumb">
            <Link href="/pool">아이디어 풀</Link> › <Link href={`/pool?source=${idea.source_id}`}>{idea.source_name}</Link> › {idea.id}
          </div>
          <h1>{idea.title}</h1>
          <div className="meta">
            {idea.category && <span className="tag">분야: {idea.category}</span>}
            {idea.used_data.slice(0, 3).map((d) => <span key={d} className="tag">당시 데이터: {d}</span>)}
            <span className="tag g">
              제출 {idea.year ?? "-"} · {idea.contest_name}{idea.award && ` · ${idea.award}`}
            </span>
            {idea.host_org && <span className="tag g">주최 {idea.host_org}</span>}
            <Link className="tag g" href={`/match?q=${encodeURIComponent(idea.title)}`}>비슷한 제목 {similar}건</Link>
          </div>
          {idea.body ? (
            <div className="desc">{idea.body}</div>
          ) : (
            <div className="desc empty">공개된 본문이 없습니다. 원본에 제목·수상 정보만 있습니다.</div>
          )}
          {(idea.problem || idea.solution) && (
            <>
              <h2>카드 요약</h2>
              {idea.problem && <p><strong>풀려던 문제</strong> {idea.problem}</p>}
              {idea.solution && <p><strong>해법</strong> {idea.solution}</p>}
            </>
          )}

          <h2>
            사업화 흔적 확인
            <small>
              판정 {TRACE[idea.trace_status ?? "pending"] ?? idea.trace_status}
              {traceText(idea.trace_status, idea.external_search) && ` · ${traceText(idea.trace_status, idea.external_search)}`}
            </small>
          </h2>
          <table>
            <thead><tr><th style={{ width: 160 }}>확인 항목</th><th style={{ width: 110 }}>결과</th><th>근거</th></tr></thead>
            <tbody>
              {TRACE_ITEMS.map((t) => (
                <tr key={t.label}>
                  <td>{t.label}</td>
                  <td>
                    {t.external && searched ? <span className="pill yes">확인함</span> : <span className="pill na">미실시</span>}
                  </td>
                  <td className="muted">
                    {t.external && searched
                      ? `${t.via} 결과는 판정에 반영됨`
                      : `${t.via} 연결 전(키 발급 대기)`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {traced && !searched && (
            <p className="note">외부 검색 없이 내부 자료로만 판정했습니다. 흔적이 없다는 뜻이 아니라 아직 찾아보지 않았다는 뜻입니다.</p>
          )}

          <h2>정체 원인 진단 <small>{diagnosis ? "담당자 검증 완료" : "검증 대기"}</small></h2>
          {diagnosis ? (
            <div className="cause">
              <div className="code">{diagnosis.cause}</div>
              <div>
                <div className="t">
                  {CAUSE[diagnosis.cause] ?? diagnosis.cause}
                  {diagnosis.secondary && (
                    <span className="muted"> · 보조 원인 {diagnosis.secondary} {CAUSE[diagnosis.secondary] ?? ""}</span>
                  )}
                </div>
                {diagnosis.rationale && <div className="e">{diagnosis.rationale}</div>}
                <div className="e"><Evidence ids={diagnosis.evidence_ids} byId={byId} /></div>
              </div>
            </div>
          ) : (
            <div className="pending">
              담당자 검증을 마친 진단만 공개합니다. 이 아이디어는 아직 검증 대기 상태입니다.
            </div>
          )}
          <a className="btn" href="#objection">사람 검증 요청</a>
          <Link className="btn o" href={`/match?q=${encodeURIComponent(idea.title)}`}>{similar > 0 ? `비슷한 아이디어 ${similar}건 비교` : "비슷한 아이디어 찾기"}</Link>
        </div>

        {/* 오른쪽: 시의성 재평가·무엇이 달라졌는가·관련 공고 */}
        <div className="stack">
          <div className="card">
            <h2>시의성 재평가 {timeliness?.as_of && <small>{timeliness.as_of} 기준</small>}</h2>
            {timeliness ? (
              <>
                <div className="score">
                  <b>{timeliness.s != null ? Number(timeliness.s).toFixed(1) : "-"}</b>
                  <span>/ 5.0</span>
                  <span className={`pill ${VERDICT_PILL[timeliness.verdict] ?? "lo"}`}>{VERDICT[timeliness.verdict] ?? timeliness.verdict}</span>
                </div>
                {AXES.map((a) => {
                  const v = timeliness[a.key];
                  return (
                    <div className="bar" key={a.key}>
                      <div>{a.label}</div>
                      <div className="tr"><div className="fl" style={{ width: v != null ? `${(v / 5) * 100}%` : 0 }} /></div>
                      <div className={v != null ? "v" : "v na"}>{v != null ? Number(v).toFixed(1) : "미채점"}</div>
                    </div>
                  );
                })}
                {timeliness.resolve_condition && <p className="note"><strong>지금 하려면</strong> {timeliness.resolve_condition}</p>}
                {timeliness.evidence_ids.length > 0 && (
                  <details className="more">
                    <summary>채점 근거 {timeliness.evidence_ids.length}건</summary>
                    <Evidence ids={timeliness.evidence_ids} byId={byId} />
                  </details>
                )}
              </>
            ) : (
              <div className="pending">아직 시의성 평가가 없습니다. 원인 진단이 검증된 뒤 네 축(기술·데이터·제도·정책)으로 채점합니다.</div>
            )}

            <h2>무엇이 달라졌는가</h2>
            {changes.length === 0 ? (
              <p className="muted">확인된 변화가 아직 없습니다.</p>
            ) : (
              <ul className="why">
                {changes.map((c) => (
                  <li key={c.id}>
                    <span className="tag g">{CHANGE_KIND[c.kind] ?? c.kind}</span>{" "}
                    {c.url ? (
                      <a href={c.url} target="_blank" rel="noopener noreferrer"><strong>{c.title}</strong></a>
                    ) : (
                      <strong>{c.title}</strong>
                    )}
                    <div className="muted">
                      {tierText(c) ?? (c.occurred_at && `${c.kind === "law_effective" ? "시행" : "발생"} ${c.occurred_at}`)}
                    </div>
                    {c.what_changed.length > 0 && <ul>{c.what_changed.map((w, i) => <li key={i}>{w}</li>)}</ul>}
                    {c.how_now && <div>{c.how_now}</div>}
                    <Evidence ids={c.evidence_ids.filter((e) => !c.url || byId.get(e)?.url !== c.url)} byId={byId} />
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <h2>관련 신규 공고 <small>유사도 상위</small></h2>
            {matches.length === 0 ? (
              <p className="muted">연결된 공고가 없습니다. 공고 수집(K-Startup·기업마당)은 키 발급 뒤 시작합니다.</p>
            ) : (
              <table>
                <tbody>
                  {matches.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <a className="link" href={m.url} target="_blank" rel="noopener noreferrer">{m.title}</a>
                        <span className="s">{m.org ?? "-"}{m.apply_to && ` · 마감 ${m.apply_to}`}</span>
                      </td>
                      <td className="num">{m.similarity != null && <span className="pill yes">{m.similarity.toFixed(2)}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <h2 id="objection">이의 제기 · 사람 검증 요청</h2>
        <p className="lead">사실이 틀렸거나 개인정보가 보이면 알려 주세요. 담당자가 확인한 뒤 반영합니다.</p>
        {objection === "ok" && <div className="notice">의견을 받았습니다. 감사합니다.</div>}
        {objection === "error" && (
          <div className="notice error">제출하지 못했습니다. 내용을 확인하고 다시 시도해 주세요.</div>
        )}
        <form method="POST" action="/api/v1/objections" className="objection-form">
          <input type="hidden" name="idea_id" value={idea.id} />
          <select name="kind" defaultValue="fact" aria-label="종류" style={{ maxWidth: 220 }}>
            {OBJECTION_KIND.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <textarea name="body" maxLength={2000} required aria-label="내용" placeholder="어떤 점이 틀렸는지 적어 주세요." />
          <button type="submit" className="btn">제출</button>
        </form>
        <h2>출처</h2>
        <p className="muted">
          {idea.source_name} ({idea.license})
          {idea.source_url && (
            <>
              {" · "}
              <a className="link" href={idea.source_url} target="_blank" rel="noopener noreferrer">원문 링크</a>
            </>
          )}
          {` · 시의성 판정 기준: S≥4.0 지금 가능 / 3.0~3.9 조건부 / 3.0 미만 보류`}
        </p>
      </div>
    </>
  );
}
