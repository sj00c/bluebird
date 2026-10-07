import { api } from "@/lib/api";
import { CAUSES, cause } from "@/lib/labels";
import { code } from "../actions";

export const dynamic = "force-dynamic";

type Coding = {
  sample_id: string;
  items: { idea_id: string; title: string; body: string | null; card_problem: string | null; missing_data: ({ name: string } | string)[] | null; my_code: string | null }[];
};

export default async function CodingPage({ searchParams }: { searchParams: Promise<{ error?: string; ok?: string }> }) {
  const sp = await searchParams;
  const c = await api<Coding>("/api/coding");
  return (
    <div className="card">
      <h1>2인 코딩</h1>
      <p className="muted">표본 {c.sample_id} · 다른 코더의 코드는 보이지 않습니다.</p>
      {sp.error && <div className="msg err">{sp.error}</div>}
      {sp.ok && <div className="msg ok">{sp.ok}</div>}
      {c.items.length === 0 && <div className="pending">배정된 표본이 없습니다.</div>}
      {c.items.map((it) => (
        <div key={it.idea_id} className="item">
          <h2>{it.title}</h2>
          <p className="muted">{it.idea_id}</p>
          {it.body && <div className="body">{it.body}</div>}
          {it.card_problem && <p><b>풀려던 문제:</b> {it.card_problem}</p>}
          {it.missing_data && it.missing_data.length > 0 && (
            <p>{it.missing_data.map((m, i) => <span key={i} className="tag">{typeof m === "string" ? m : m.name}</span>)}</p>
          )}
          {it.my_code && <p><span className="tag">내 코드: {cause(it.my_code)}</span></p>}
          <form action={code} className="stack">
            <input type="hidden" name="idea_id" value={it.idea_id} />
            <label>
              막힌 이유
              <select name="code" defaultValue={it.my_code ?? ""} required>
                <option value="" disabled>선택</option>
                {Object.entries(CAUSES).map(([k, v]) => <option key={k} value={k}>{k} {v}</option>)}
              </select>
            </label>
            <label>
              메모
              <textarea name="note" />
            </label>
            <div className="actions"><button type="submit">{it.my_code ? "코드 다시 저장" : "코드 저장"}</button></div>
          </form>
        </div>
      ))}
    </div>
  );
}
