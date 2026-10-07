import Link from "next/link";
import { notFound } from "next/navigation";
import { getIdea } from "@/lib/db";

export default async function IdeaPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const idea = await getIdea(id);
  if (!idea) notFound();

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
      <div className="pending">담당자 검증을 마친 진단만 공개합니다. 이 아이디어는 아직 검증 대기 상태입니다.</div>
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
