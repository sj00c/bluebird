import Link from "next/link";
import { api } from "@/lib/api";
import { cause, VERDICTS } from "@/lib/labels";

export const dynamic = "force-dynamic";

type Item = {
  idea_id: string;
  title: string;
  year: number | null;
  source_id: string;
  cause: string | null;
  stage: string;
  s: number | null;
  verdict: string | null;
};
type Queue = { items: Item[]; counts: Record<string, number> };

const STAGES = ["s2", "s3", "s4", "s5", "s6"];
const STAGE_NAMES: Record<string, string> = {
  s2: "2단계 통과",
  s3: "3단계 통과",
  s4: "4단계 통과",
  s5: "5단계 통과",
  s6: "6단계 통과",
};

export default async function QueuePage({ searchParams }: { searchParams: Promise<{ stage?: string }> }) {
  const sp = await searchParams;
  const stage = sp.stage && STAGES.includes(sp.stage) ? sp.stage : "s4";
  const q = await api<Queue>(`/api/queue?stage=${stage}&limit=50`);
  return (
    <div className="card">
      <h1>검토 대기</h1>
      <div className="pills">
        {STAGES.map((s) => (
          <Link key={s} href={`/?stage=${s}`} className={s === stage ? "on" : ""}>
            {STAGE_NAMES[s]}
          </Link>
        ))}
      </div>
      <div className="counts">
        {Object.entries(q.counts).map(([k, v]) => (
          <span key={k}>{k} <b>{v.toLocaleString("ko-KR")}</b></span>
        ))}
      </div>
      {q.items.length === 0 ? (
        <div className="pending">이 단계에 해당하는 아이디어가 없습니다.</div>
      ) : (
        <table>
          <thead>
            <tr><th>아이디어</th><th>연도</th><th>출처</th><th>막힌 이유</th><th>S</th><th>판정</th></tr>
          </thead>
          <tbody>
            {q.items.map((it) => (
              <tr key={it.idea_id}>
                <td>
                  <Link href={`/ideas/${encodeURIComponent(it.idea_id)}`}>{it.title}</Link>
                  <div className="muted">{it.idea_id}</div>
                </td>
                <td>{it.year ?? "-"}</td>
                <td>{it.source_id}</td>
                <td>{cause(it.cause)}</td>
                <td>{it.s ?? "-"}</td>
                <td>{it.verdict ? (VERDICTS[it.verdict] ?? it.verdict) : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
