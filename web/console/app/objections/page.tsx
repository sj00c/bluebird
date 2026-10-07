import Link from "next/link";
import { api } from "@/lib/api";
import { OBJECTION_KINDS, OBJECTION_STATUS, when } from "@/lib/labels";
import { resolveObjection } from "../actions";

export const dynamic = "force-dynamic";

type Item = {
  id: number | string;
  idea_id: string;
  title: string;
  kind: string;
  body: string;
  status: string;
  submitted_at: string;
  pulled_at: string | null;
  resolution: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
};

const STATUSES = ["open", "accepted", "rejected"];

export default async function ObjectionsPage({ searchParams }: { searchParams: Promise<{ status?: string; error?: string; ok?: string }> }) {
  const sp = await searchParams;
  const status = sp.status && STATUSES.includes(sp.status) ? sp.status : "open";
  const { items } = await api<{ items: Item[] }>(`/api/objections?status=${status}`);
  return (
    <div className="card">
      <h1>이의 처리</h1>
      <div className="pills">
        {STATUSES.map((s) => (
          <Link key={s} href={`/objections?status=${s}`} className={s === status ? "on" : ""}>{OBJECTION_STATUS[s]}</Link>
        ))}
      </div>
      {sp.error && <div className="msg err">{sp.error}</div>}
      {sp.ok && <div className="msg ok">{sp.ok}</div>}
      {items.length === 0 && <div className="pending">해당 상태의 이의가 없습니다.</div>}
      {items.map((o) => (
        <div key={o.id} className="item">
          <p>
            <Link href={`/ideas/${encodeURIComponent(o.idea_id)}`} className="lnk">{o.title}</Link>{" "}
            <span className="tag">{OBJECTION_KINDS[o.kind] ?? o.kind}</span>
            <span className="tag">{OBJECTION_STATUS[o.status] ?? o.status}</span>
          </p>
          <p className="muted">접수 {when(o.submitted_at)} · 가져옴 {when(o.pulled_at)}</p>
          <div className="body">{o.body}</div>
          {o.status !== "open" ? (
            <p className="muted">
              처리 {when(o.resolved_at)} · {o.resolved_by ?? "-"}
              {o.resolution && <><br />{o.resolution}</>}
            </p>
          ) : (
            <form action={resolveObjection} className="stack">
              <input type="hidden" name="objection_id" value={String(o.id)} />
              <label>
                결정
                <select name="decision" defaultValue="" required>
                  <option value="" disabled>선택</option>
                  <option value="accepted">수용 (공개 승인 철회)</option>
                  <option value="rejected">기각</option>
                </select>
              </label>
              <label>
                처리 내용 (필수, 공개될 수 있음)
                <textarea name="resolution" required />
              </label>
              <label className="check">
                <input type="checkbox" name="withhold" />
                원본까지 공개 중단 (개인정보 등)
              </label>
              <div className="actions"><button type="submit">처리</button></div>
            </form>
          )}
        </div>
      ))}
    </div>
  );
}
