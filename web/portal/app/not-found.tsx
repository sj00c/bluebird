import Link from "next/link";

export default function NotFound() {
  return (
    <section className="card state-panel">
      <p className="eyebrow">404</p>
      <h1>페이지 없음</h1>
      <ul className="checklist">
        <li>가능한 원인: 주소 변경·공개 보류</li>
        <li>공개 자료: 아이디어 풀에서 조회</li>
      </ul>
      <Link className="btn" href="/pool">
        아이디어 풀
      </Link>
      <Link className="btn o" href="/">
        아이디어 작업대
      </Link>
    </section>
  );
}
