"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="card state-panel" role="alert">
      <h1>화면 조회 실패</h1>
      <ul className="instructions">
        <li>가능한 원인: API 연결 또는 서버 처리 오류</li>
        <li>데이터 없음 상태와 별개</li>
        <li>재시도 후 지속되면 운영자에게 API 상태 확인 요청</li>
      </ul>
      {error.digest && (
        <p className="provenance">오류 식별 번호: {error.digest}</p>
      )}
      <button type="button" onClick={reset}>
        다시 불러오기
      </button>
    </section>
  );
}
