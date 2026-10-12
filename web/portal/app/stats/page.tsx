import {
  cardKindStats,
  poolOverview,
  sourceStats,
  yearStats,
} from "@/lib/statistics";
import { CAUSE, VERDICT } from "@/lib/labels";
import { PageHeading, TableScroll } from "../components";

export const dynamic = "force-dynamic";

const CARD_KIND: Record<string, string> = {
  full: "전체 카드(AI 요약)",
  local_extract: "본문 규칙 추출",
  title_only: "제목만",
};

function Bars({ rows }: { rows: { label: string; n: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  const total = rows.reduce((a, r) => a + r.n, 0);
  if (rows.length === 0) return <p className="pending">집계 데이터 없음</p>;
  return (
    <div className="dist wide">
      {rows.map((r) => (
        <div className="row" key={r.label}>
          <span>{r.label}</span>
          <div className="tr">
            <div className="fl" style={{ width: `${(r.n / max) * 100}%` }} />
          </div>
          <span className="v">
            {r.n.toLocaleString("ko-KR")} (
            {total ? Math.round((r.n / total) * 100) : 0}%)
          </span>
        </div>
      ))}
    </div>
  );
}

export default async function StatsPage() {
  const [o, sources, years, kinds] = await Promise.all([
    poolOverview(),
    sourceStats(),
    yearStats(),
    cardKindStats(),
  ]);
  return (
    <>
      <PageHeading eyebrow="데이터 관리" title="출처·통계">
        공개 DB 기준 · 수집·검색·검증 단계별 집계
      </PageHeading>
      <div className="card">
        <h2>공개 현황</h2>
        <div className="kpi k6">
          <div>
            <b>{o.ideas.toLocaleString("ko-KR")}</b>
            <span>공개 아이디어</span>
          </div>
          <div>
            <b>{o.sources}</b>
            <span>출처</span>
          </div>
          <div>
            <b>{o.externalSearched.toLocaleString("ko-KR")}</b>
            <span>외부 흔적 검색</span>
          </div>
          <div>
            <b>{o.verified.toLocaleString("ko-KR")}</b>
            <span>원인 진단 검증</span>
          </div>
          <div>
            <b>{o.scored.toLocaleString("ko-KR")}</b>
            <span>시의성 채점</span>
          </div>
          <div>
            <b>{o.announcements.toLocaleString("ko-KR")}</b>
            <span>수집 공고</span>
          </div>
        </div>
        <p className="note">
          집계 제외: 공개 보류·약관 확인 중인 출처의 아이디어
        </p>
      </div>

      <div className="stats-layout">
        <div className="stack">
          <div className="card">
            <h2>카드 종류</h2>
            <Bars
              rows={kinds.map((k) => ({
                label: CARD_KIND[k.card_kind] ?? k.card_kind,
                n: k.n,
              }))}
            />
          </div>
          <div className="card">
            <h2>
              정체 원인 <small>검증 {o.verified}건</small>
            </h2>
            {o.causes.length === 0 ? (
              <p className="muted">검증 진단 없음</p>
            ) : (
              <Bars
                rows={o.causes.map((c) => ({
                  label: `${c.cause} ${CAUSE[c.cause] ?? ""}`,
                  n: c.n,
                }))}
              />
            )}
            <h2>
              시의성 판정 <small>채점 {o.scored}건</small>
            </h2>
            {o.verdicts.length === 0 ? (
              <p className="muted">평가 결과 없음</p>
            ) : (
              <Bars
                rows={o.verdicts.map((v) => ({
                  label: VERDICT[v.verdict] ?? v.verdict,
                  n: v.n,
                }))}
              />
            )}
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <h2>출처별</h2>
            {sources.length === 0 ? (
              <p className="pending">공개 출처 없음</p>
            ) : (
              <TableScroll label="출처별 공개 현황">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">출처</th>
                      <th scope="col">이용 조건</th>
                      <th scope="col" className="num">
                        아이디어
                      </th>
                      <th scope="col" className="num">
                        본문 공개 비율
                      </th>
                      <th scope="col">연도</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <a
                            className="link"
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {s.name}
                          </a>
                        </td>
                        <td className="muted">{s.license}</td>
                        <td className="num">
                          {s.ideas.toLocaleString("ko-KR")}
                        </td>
                        <td className="num">
                          {s.ideas
                            ? Math.round((s.with_body / s.ideas) * 100)
                            : 0}
                          %
                        </td>
                        <td className="nw">
                          {s.y_min ?? "-"}–{s.y_max ?? "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            )}
          </div>
          <div className="card">
            <h2>제출 연도별</h2>
            <Bars
              rows={years.map((y) => ({ label: String(y.year), n: y.n }))}
            />
          </div>
        </div>
      </div>
    </>
  );
}
