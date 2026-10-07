import Link from "next/link";
import { api } from "@/lib/api";
import { cause, CHANGE_KINDS, DECISIONS, OBJECTION_KINDS, OBJECTION_STATUS, ROUNDS, STAGES, VERDICTS, when } from "@/lib/labels";
import { review } from "../../actions";

export const dynamic = "force-dynamic";

type Detail = {
  idea: { id: string; title: string; body: string | null; year: number | null; award: string | null; contest: string | null; source_id: string; public_ok: boolean };
  card: { card_kind: string | null; problem: string | null; solution: string | null; missing_data: { name: string; excerpt: string | null }[]; extractor: string | null } | null;
  trace: { status: string | null; profile_version: string | null; checks: { item: string; result: string; detail: Record<string, unknown> | null }[] } | null;
  diagnosis: { cause: string; secondary: string | null; rationale: string | null; extractor: string | null; decided_by: string | null; evidence: { url: string; excerpt: string | null }[] } | null;
  matches: {
    id: number | string; change_id: number | string; kind: string; title: string; url: string | null; occurred_at: string | null;
    verify_status: string | null; llm_verdict: string | null; status: string | null; what_changed: string[]; how_now: string | null; eligible: boolean;
  }[];
  timeliness: { as_of: string | null; tech: number | null; data: number | null; regulation: number | null; policy: number | null; n_scored: number | null; s: number | null; verdict: string | null; resolve_condition: string | null; scored_by: string | null } | null;
  stage: Record<string, boolean>;
  reviews: { round: string; reviewer: string; decision: string; code: string | null; note: string | null; created_at: string }[];
  objections: { id: number | string; kind: string; body: string; status: string; resolution: string | null; submitted_at: string; resolved_at: string | null }[];
};

function Link2({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noopener noreferrer" className="lnk">{children}</a>;
}

function ReviewForm({ id, round, decision, label, noteRequired, danger }: { id: string; round: string; decision: string; label: string; noteRequired?: boolean; danger?: boolean }) {
  return (
    <form action={review} className="stack item">
      <input type="hidden" name="idea_id" value={id} />
      <input type="hidden" name="round" value={round} />
      <input type="hidden" name="decision" value={decision} />
      <label>
        {noteRequired ? "사유 (필수)" : "메모 (선택)"}
        <textarea name="note" required={noteRequired} />
      </label>
      <div className="actions"><button type="submit" className={danger ? "danger" : undefined}>{label}</button></div>
    </form>
  );
}

export default async function IdeaPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string; ok?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const d = await api<Detail>(`/api/ideas/${encodeURIComponent(id)}`);
  const { idea, card, trace, diagnosis, timeliness } = d;

  return (
    <>
      <div className="card">
        <p className="muted"><Link href="/">검토 대기</Link> › {idea.id}</p>
        <h1>{idea.title}</h1>
        {sp.error && <div className="msg err">{sp.error}</div>}
        {sp.ok && <div className="msg ok">{sp.ok}</div>}
        <div className="stages">
          {STAGES.map((s) => (
            <span key={s} className={d.stage[s] ? "stage on" : "stage"}>{s}</span>
          ))}
        </div>
        <div>
          <span className="tag">연도 {idea.year ?? "-"}</span>
          {idea.contest && <span className="tag">{idea.contest}</span>}
          {idea.award && <span className="tag">{idea.award}</span>}
          <span className="tag">출처 {idea.source_id}</span>
          <span className="tag">{idea.public_ok ? "공개 중" : "비공개"}</span>
        </div>
        <h2>원본</h2>
        {idea.body ? <div className="body">{idea.body}</div> : <div className="pending">본문이 없습니다.</div>}
      </div>

      <div className="card">
        <h2>카드</h2>
        {card ? (
          <>
            <p className="muted">종류 {card.card_kind ?? "-"} · 추출 {card.extractor ?? "-"}</p>
            <h2>풀려던 문제</h2>
            <div className="body">{card.problem ?? "-"}</div>
            <h2>해법</h2>
            <div className="body">{card.solution ?? "-"}</div>
            <h2>필요했던 데이터</h2>
            {card.missing_data.length === 0 ? <p className="muted">없음</p> : card.missing_data.map((m) => (
              <div key={m.name}><span className="tag">{m.name}</span>{m.excerpt && <span className="muted">{m.excerpt}</span>}</div>
            ))}
          </>
        ) : <div className="pending">카드가 아직 없습니다.</div>}

        <h2>흔적</h2>
        {trace ? (
          <>
            <p className="muted">상태 {trace.status ?? "-"} · 프로파일 {trace.profile_version ?? "-"}</p>
            {trace.checks.length > 0 && (
              <table>
                <thead><tr><th>항목</th><th>결과</th><th>내용</th></tr></thead>
                <tbody>
                  {trace.checks.map((c, i) => (
                    <tr key={i}><td>{c.item}</td><td>{c.result}</td><td>{checkDetail(c.detail)}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : <div className="pending">흔적 확인 결과가 아직 없습니다.</div>}

        <h2>막힌 이유</h2>
        {diagnosis ? (
          <>
            <p>
              <span className="tag">{cause(diagnosis.cause)}</span>
              {diagnosis.secondary && <span className="tag">보조 {cause(diagnosis.secondary)}</span>}
              <span className="muted">추출 {diagnosis.extractor ?? "-"} · 결정 {diagnosis.decided_by ?? "-"}</span>
            </p>
            {diagnosis.rationale && <div className="body">{diagnosis.rationale}</div>}
            {diagnosis.evidence.length > 0 && (
              <>
                <h2>근거</h2>
                <ul>
                  {diagnosis.evidence.map((e, i) => (
                    <li key={i}><Link2 href={e.url}>{e.url}</Link2>{e.excerpt && <div className="muted">{e.excerpt}</div>}</li>
                  ))}
                </ul>
              </>
            )}
          </>
        ) : <div className="pending">진단이 아직 없습니다.</div>}
      </div>

      <div className="card">
        <h2>바뀐 것 매칭</h2>
        {d.matches.length === 0 ? <div className="pending">매칭된 변화가 없습니다.</div> : (
          <table>
            <thead><tr><th>변화</th><th>일자</th><th>확인</th><th>LLM 판정</th><th>상태</th><th>사용 가능</th></tr></thead>
            <tbody>
              {d.matches.map((m) => (
                <tr key={m.id}>
                  <td>
                    <span className="tag">{CHANGE_KINDS[m.kind] ?? m.kind}</span>
                    {m.url ? <Link2 href={m.url}>{m.title}</Link2> : m.title}
                    {m.what_changed.length > 0 && <ul>{m.what_changed.map((w, i) => <li key={i}>{w}</li>)}</ul>}
                    {m.how_now && <div className="muted">지금은: {m.how_now}</div>}
                  </td>
                  <td>{m.occurred_at ?? "-"}</td>
                  <td>{m.verify_status ?? "-"}</td>
                  <td>{m.llm_verdict ?? "-"}</td>
                  <td>{m.status ?? "-"}</td>
                  <td>{m.eligible ? "예" : "아니오"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h2>시의성 (S)</h2>
        {timeliness ? (
          <>
            <p>
              <b>S {timeliness.s ?? "-"}</b>{" "}
              <span className="tag">{timeliness.verdict ? (VERDICTS[timeliness.verdict] ?? timeliness.verdict) : "-"}</span>
              <span className="muted">기준일 {timeliness.as_of ?? "-"} · 채점 {timeliness.scored_by ?? "-"} · 채점 항목 {timeliness.n_scored ?? "-"}개</span>
            </p>
            <p>
              <span className="tag">기술 {timeliness.tech ?? "-"}</span>
              <span className="tag">데이터 {timeliness.data ?? "-"}</span>
              <span className="tag">규제 {timeliness.regulation ?? "-"}</span>
              <span className="tag">정책 {timeliness.policy ?? "-"}</span>
            </p>
            {timeliness.resolve_condition && <div className="body">{timeliness.resolve_condition}</div>}
          </>
        ) : <div className="pending">시의성 점수가 아직 없습니다.</div>}
      </div>

      <div className="card">
        <h2>검토 기록</h2>
        {d.reviews.length === 0 ? <div className="pending">검토 기록이 없습니다.</div> : (
          <table>
            <thead><tr><th>라운드</th><th>검토자</th><th>결정</th><th>코드</th><th>메모</th><th>시각</th></tr></thead>
            <tbody>
              {d.reviews.map((r, i) => (
                <tr key={i}>
                  <td>{ROUNDS[r.round] ?? r.round}</td>
                  <td>{r.reviewer}</td>
                  <td>{DECISIONS[r.decision] ?? r.decision}</td>
                  <td>{r.code ? cause(r.code) : "-"}</td>
                  <td>{r.note ?? ""}</td>
                  <td>{when(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h2>이의</h2>
        {d.objections.length === 0 ? <div className="pending">접수된 이의가 없습니다.</div> : d.objections.map((o) => (
          <div key={o.id} className="item">
            <span className="tag">{OBJECTION_KINDS[o.kind] ?? o.kind}</span>
            <span className="tag">{OBJECTION_STATUS[o.status] ?? o.status}</span>
            <span className="muted">접수 {when(o.submitted_at)}{o.resolved_at && ` · 처리 ${when(o.resolved_at)}`}</span>
            <div className="body">{o.body}</div>
            {o.resolution && <p className="muted">처리 내용: {o.resolution}</p>}
          </div>
        ))}
      </div>

      <div className="card">
        <h2>최종 승인</h2>
        <ReviewForm id={idea.id} round="final" decision="approve" label="최종 승인" />
        <h2>반려</h2>
        <ReviewForm id={idea.id} round="final" decision="reject" label="반려" noteRequired danger />
        <h2>전문가·감사 라운드</h2>
        <form action={review} className="stack item">
          <input type="hidden" name="idea_id" value={idea.id} />
          <input type="hidden" name="decision" value="approve" />
          <label>
            메모 (선택)
            <textarea name="note" />
          </label>
          <div className="actions">
            <button type="submit" name="round" value="expert" className="sub">
              전문가 승인
            </button>
            <button type="submit" name="round" value="audit" className="sub">
              감사 승인
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

// trace_check.detail(jsonb): 사람 확인은 {by, note, url}, 자동 점검은 건수 등. 키=값으로 보여준다.
function checkDetail(d: Record<string, unknown> | null): string {
  if (!d) return "";
  return Object.entries(d)
    .filter(([, v]) => v !== null && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(" · ");
}
