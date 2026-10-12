import Link from "next/link";
import { timelinessList } from "@/lib/revival";
import { AXES, CAUSE, VERDICT, VERDICT_PILL } from "@/lib/labels";
import { PageHeading, TableScroll } from "../components";

export const dynamic = "force-dynamic";

// 원인 코드 T·D·R·M은 시의성 네 축과 1:1로 대응한다(원인이 풀렸는지를 같은 축으로 잰다).
const CAUSE_AXIS: Record<string, string> = {
  T: "tech",
  D: "data",
  R: "regulation",
  M: "policy",
};

export default async function TimelinessPage() {
  const rows = await timelinessList();
  return (
    <>
      <PageHeading eyebrow="검증 분석" title="시의성 평가">
        기술·데이터·제도·정책 · 점수 높은 순
      </PageHeading>
      <div className="card">
        <h2>
          평가 목록 <small>{rows.length}건 · 축별 0~5점</small>
        </h2>
        <ul className="checklist">
          <li>지금 가능: S ≥ 4</li>
          <li>조건부: 3 ≤ S &lt; 4</li>
          <li>보류: S &lt; 3 · 채점 축 2개 미만</li>
          <li>강조 축: 원인 진단과 일치</li>
        </ul>
        {rows.length === 0 ? (
          <div className="pending">
            평가 결과 없음{" "}
            <Link className="link" href="/pool?verified=1">
              검증 진단 목록
            </Link>
          </div>
        ) : (
          <TableScroll label="아이디어별 시의성 비교">
            <table className="score-table">
              <thead>
                <tr>
                  <th>아이디어(익명 처리)</th>
                  <th>원인</th>
                  {AXES.map((a) => (
                    <th key={a.key} className="num">
                      {a.label}
                    </th>
                  ))}
                  <th className="num">S</th>
                  <th>판정</th>
                  <th>기준일</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.idea_id}>
                    <td>
                      <Link
                        className="n"
                        href={`/ideas/${encodeURIComponent(r.idea_id)}`}
                      >
                        {r.title}
                      </Link>
                      <span className="s">
                        {r.year ?? "-"} · {r.contest_name}
                      </span>
                      {r.resolve_condition && (
                        <details className="more">
                          <summary>충족 조건</summary>
                          <div className="desc">{r.resolve_condition}</div>
                        </details>
                      )}
                    </td>
                    <td className="nw">
                      {r.cause ? (
                        <span
                          className={`cd ${r.cause}`}
                          title={CAUSE[r.cause]}
                        >
                          {r.cause}
                        </span>
                      ) : (
                        "-"
                      )}
                    </td>
                    {AXES.map((a) => {
                      const v = r[a.key];
                      const own = r.cause && CAUSE_AXIS[r.cause] === a.key;
                      return (
                        <td
                          key={a.key}
                          className={`num${own ? " axis-own" : ""}`}
                        >
                          {v != null ? (
                            Number(v).toFixed(1)
                          ) : (
                            <span className="muted">미채점</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="sc num">
                      {r.s != null ? Number(r.s).toFixed(1) : "-"}
                    </td>
                    <td className="nw">
                      <span
                        className={`pill ${VERDICT_PILL[r.verdict] ?? "lo"}`}
                      >
                        {VERDICT[r.verdict] ?? r.verdict}
                      </span>
                    </td>
                    <td className="nw muted">{r.as_of ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        )}
        <ul className="checklist note">
          <li>평가 대상: 검증 진단·변화 연결 완료</li>
          <li>미채점: 0점과 구분</li>
          <li>점수: 사업 성공 예측·보장 아님</li>
          <li>기준일·근거: 아이디어 상세에서 확인</li>
        </ul>
      </div>
    </>
  );
}
