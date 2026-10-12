import Link from "next/link";
import { notFound } from "next/navigation";
import { announcementMatches, similarCount } from "@/lib/exploration";
import { getIdea } from "@/lib/ideas";
import { getRevival } from "@/lib/revival";
import { CAUSE, TRACE, TRACE_ITEMS, traceText } from "@/lib/labels";
import { TableScroll } from "../../components";
import { ObjectionForm } from "./objection-form";
import { Evidence } from "./evidence";
import { RevivalReview } from "./revival-review";

export const dynamic = "force-dynamic";

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
  const [{ diagnosis, changes, timeliness, evidence }, similar, matches] =
    await Promise.all([
      getRevival(id),
      similarCount(id, idea.title),
      announcementMatches(id),
    ]);
  const byId = new Map(evidence.map((e) => [e.id, e]));
  const searched = idea.external_search === "done";
  const traced = idea.trace_status && idea.trace_status !== "pending";

  return (
    <>
      <nav className="detail-nav" aria-label="아이디어 상세 목차">
        <a href="#original">공개 원본</a>
        <a href="#trace">사업화 흔적</a>
        <a href="#diagnosis">정체 원인</a>
        <a href="#timeliness">시의성</a>
        <a href="#changes">확인된 변화</a>
        <a href="#objection">검증 의견</a>
      </nav>
      <div className="cols-a detail-reading">
        <article className="card">
          <div className="crumb">
            <Link href="/pool">아이디어 풀</Link> /{" "}
            <Link href={`/pool?source=${encodeURIComponent(idea.source_id)}`}>
              {idea.source_name}
            </Link>{" "}
            / {idea.id}
          </div>
          <h1>{idea.title}</h1>
          <p className="detail-status">
            <span className={`tag ${diagnosis ? "" : "g"}`}>
              {diagnosis
                ? "담당자 검증 진단 공개"
                : "공개 원본 · 진단 검증 대기"}
            </span>
          </p>
          <div className="meta">
            {idea.category && (
              <span className="tag">분야: {idea.category}</span>
            )}
            {idea.used_data.slice(0, 3).map((d) => (
              <span key={d} className="tag">
                당시 데이터: {d}
              </span>
            ))}
            <span className="tag g">
              제출 {idea.year ?? "-"} · {idea.contest_name}
              {idea.award && ` · ${idea.award}`}
            </span>
            {idea.host_org && (
              <span className="tag g">주최 {idea.host_org}</span>
            )}
            {similar != null && (
              <span className="tag g">비슷한 제목 {similar}건</span>
            )}
          </div>
          <h2 id="original">공개 원본</h2>
          {idea.body ? (
            <details className="more">
              <summary>원문 보기 · 개인정보 익명 처리</summary>
              <div className="desc">{idea.body}</div>
            </details>
          ) : (
            <div className="desc empty">
              본문 미공개 · 제목·수상 정보만 제공
            </div>
          )}
          {(idea.problem || idea.solution) && (
            <>
              <h2>
                카드 요약 <small>원본과 별도</small>
              </h2>
              <details className="more">
                <summary>문제·해법</summary>
                <dl className="record-facts">
                  {idea.problem && (
                    <div>
                      <dt>문제</dt>
                      <dd>{idea.problem}</dd>
                    </div>
                  )}
                  {idea.solution && (
                    <div>
                      <dt>해법</dt>
                      <dd>{idea.solution}</dd>
                    </div>
                  )}
                </dl>
              </details>
            </>
          )}

          <h2 id="trace">
            사업화 흔적 확인
            <small>
              판정 {TRACE[idea.trace_status ?? "pending"] ?? idea.trace_status}
              {traceText(idea.trace_status, idea.external_search) &&
                ` · ${traceText(idea.trace_status, idea.external_search)}`}
            </small>
          </h2>
          <ul className="checklist note">
            <li>외부 검색: {searched ? "실시 기록 있음" : "실시 기록 없음"}</li>
            <li>
              {searched
                ? "검색 실시 ≠ 개별 결과 확인·사업화"
                : "미실시 ≠ 검색 결과 없음"}
            </li>
          </ul>
          <TableScroll label="사업화 흔적 확인 범위">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 160 }}>확인 항목</th>
                  <th style={{ width: 110 }}>결과</th>
                  <th>근거</th>
                </tr>
              </thead>
              <tbody>
                {TRACE_ITEMS.map((t) => (
                  <tr key={t.label}>
                    <td>{t.label}</td>
                    <td>
                      {t.external && searched ? (
                        <span className="pill yes">통합 검색 실시</span>
                      ) : (
                        <span className="pill na">
                          {t.external ? "미실시" : "확인 기록 미공개"}
                        </span>
                      )}
                    </td>
                    <td className="muted">
                      {t.external && searched
                        ? `${t.via} · 개별 근거 미공개`
                        : t.external
                          ? `${t.via} · 실시 여부 미확인`
                          : `${t.via} · 공고 연결 ≠ 선정 이력`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          {traced && !searched && (
            <p className="note">판정 범위: 내부 자료 · 외부 흔적 미확인</p>
          )}

          <h2 id="diagnosis">
            정체 원인 진단{" "}
            <small>{diagnosis ? "담당자 검증 완료" : "검증 대기"}</small>
          </h2>
          {diagnosis ? (
            <div className="cause">
              <div className="code">{diagnosis.cause}</div>
              <div>
                <div className="t">
                  {CAUSE[diagnosis.cause] ?? diagnosis.cause}
                  {diagnosis.secondary && (
                    <span className="muted">
                      {" "}
                      · 보조 원인 {diagnosis.secondary}{" "}
                      {CAUSE[diagnosis.secondary] ?? ""}
                    </span>
                  )}
                </div>
                <details className="more">
                  <summary>진단 사유·근거</summary>
                  {diagnosis.rationale && (
                    <div className="e">{diagnosis.rationale}</div>
                  )}
                  <Evidence ids={diagnosis.evidence_ids} byId={byId} />
                </details>
              </div>
            </div>
          ) : (
            <div className="pending">진단 검증 대기 · 승인된 분석만 공개</div>
          )}
          <a className="btn" href="#objection">
            검증 요청
          </a>
          <Link
            className="btn o"
            href={`/match?q=${encodeURIComponent(idea.title)}`}
          >
            유사 아이디어
          </Link>
        </article>

        <div className="stack">
          <RevivalReview
            timeliness={timeliness}
            changes={changes}
            evidence={byId}
          />

          <div className="card">
            <h2>
              관련 신규 공고 <small>유사도 상위</small>
            </h2>
            {matches.length === 0 ? (
              <p className="muted">
                연결 공고 없음{" "}
                <Link
                  className="link"
                  href={`/match?q=${encodeURIComponent(idea.title)}`}
                >
                  주제 검색
                </Link>
              </p>
            ) : (
              <TableScroll label="관련 신규 공고">
                <table>
                  <tbody>
                    {matches.map((m) => (
                      <tr key={m.id}>
                        <td>
                          <a
                            className="link"
                            href={m.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {m.title}
                          </a>
                          <span className="s">
                            {m.org ?? "-"}
                            {m.apply_to && ` · 마감 ${m.apply_to}`}
                          </span>
                        </td>
                        <td className="num">
                          {m.similarity != null && (
                            <span className="pill yes">
                              {m.similarity.toFixed(2)}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <h2 id="objection">검증 의견</h2>
        <ul className="checklist">
          <li>접수 대상: 사실 오류·진단·변화·개인정보</li>
          <li>처리: 담당자 검토 후 반영</li>
        </ul>
        <ObjectionForm ideaId={idea.id} initialStatus={objection} />
        <h2>출처</h2>
        <p className="muted">
          {idea.source_name} ({idea.license})
          {idea.source_url && (
            <>
              {" · "}
              <a
                className="link"
                href={idea.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                원문 링크
              </a>
            </>
          )}
        </p>
      </div>
    </>
  );
}
