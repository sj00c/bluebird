"use client";

// 서버 오류 메시지는 운영 빌드에서 가려진다(digest만). 내용은 backend-api 로그로 확인한다.
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <>
      <h1>요청을 처리하지 못했습니다</h1>
      <p className="muted">잠시 뒤 다시 시도하세요.{error.digest ? ` (오류 번호 ${error.digest})` : ""}</p>
      <button type="button" onClick={reset}>다시 시도</button>
    </>
  );
}
