import Link from "next/link";
import { timelinessList } from "@/lib/db";
import { AXES, CAUSE, VERDICT, VERDICT_PILL } from "@/lib/labels";

export const dynamic = "force-dynamic";

// 원인 코드 T·D·R·M은 시의성 네 축과 1:1로 대응한다(원인이 풀렸는지를 같은 축으로 잰다).
const CAUSE_AXIS: Record<string, string> = { T: "tech", D: "data", R: "regulation", M: "policy" };

export default async function TimelinessPage() {
  const rows = await timelinessList();
  return (
    <>
      <div className="card">
        <h2>시의성 재평가 <small>지금 다시 해볼 만한가 · 네 축 0~5점</small></h2>
        <p className="lead">
          막힌 원인(기술·데이터·제도·수요)이 지금은 풀렸는지를 같은 네 축으로 다시 잽니다. 채점한 축마다 근거 문서가 붙고,
          S가 4.0 이상이면 지금 가능, 3.0~3.9는 조건부, 3.0 미만은 보류입니다. 막힌 원인과 같은 축은 굵게 표시합니다.
        </p>
        {rows.length === 0 ? (
          <div className="pending">채점을 마친 아이디어가 아직 없습니다.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>아이디어(익명 처리)</th><th>원인</th>
                {AXES.map((a) => <th key={a.key} className="num">{a.label}</th>)}
                <th className="num">S</th><th>판정</th><th>기준일</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.idea_id}>
                  <td>
                    <Link className="n" href={`/ideas/${r.idea_id}`}>{r.title}</Link>
                    <span className="s">{r.year ?? "-"} · {r.contest_name}</span>
                    {r.resolve_condition && <span className="s">{r.resolve_condition}</span>}
                  </td>
                  <td className="nw">{r.cause ? <span className={`cd ${r.cause}`} title={CAUSE[r.cause]}>{r.cause}</span> : "-"}</td>
                  {AXES.map((a) => {
                    const v = r[a.key];
                    const own = r.cause && CAUSE_AXIS[r.cause] === a.key;
                    return (
                      <td key={a.key} className="num" style={own ? { fontWeight: 800, color: "#0f2557" } : undefined}>
                        {v != null ? Number(v).toFixed(1) : <span className="muted">미채점</span>}
                      </td>
                    );
                  })}
                  <td className="sc num">{r.s != null ? Number(r.s).toFixed(1) : "-"}</td>
                  <td className="nw"><span className={`pill ${VERDICT_PILL[r.verdict] ?? "lo"}`}>{VERDICT[r.verdict] ?? r.verdict}</span></td>
                  <td className="nw muted">{r.as_of ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="note">
          채점은 원인 진단이 검증되고 바뀐 것이 연결된 아이디어부터 합니다. 두 축 미만이 채점되면 판단 불가(보류)입니다.
        </p>
      </div>
    </>
  );
}
