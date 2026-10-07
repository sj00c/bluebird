import Link from "next/link";

export default function Forbidden() {
  return (
    <>
      <h1>권한이 없습니다</h1>
      <p className="muted">이 화면은 맡은 역할로 볼 수 없습니다. 코더는 독립 코딩을 위해 검토 큐·상세(예측 원인)를 볼 수 없습니다.</p>
      <p><Link href="/coding">2인 코딩으로</Link></p>
    </>
  );
}
