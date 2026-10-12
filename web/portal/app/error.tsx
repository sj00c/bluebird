"use client";

import Link from "next/link";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="card state-panel" role="alert">
      <p className="eyebrow">연결 오류</p>
      <h1>데이터 조회 실패</h1>
      <ul className="checklist">
        <li>데이터 유무: 확인 불가</li>
        <li>복구: 잠시 후 다시 불러오기</li>
        <li>검증 의견: 접수 여부 확인 전 중복 제출 주의</li>
      </ul>
      <button className="btn" onClick={reset}>
        다시 불러오기
      </button>
      <Link className="btn o" href="/">
        아이디어 작업대
      </Link>
    </section>
  );
}
