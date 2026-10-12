import { login } from "../actions";
import { Submit } from "../action-form";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  return (
    <section className="card login-card">
      <h1>운영 콘솔 로그인</h1>
      <ul className="instructions" id="token-help">
        <li>운영자 발급 접근 토큰 필요</li>
        <li>역할별 메뉴·작업 권한 적용</li>
      </ul>
      {error && (
        <div className="msg err" role="alert">
          {error}
        </div>
      )}
      <form action={login} className="stack">
        <label>
          접근 토큰
          <input
            type="password"
            name="token"
            autoComplete="current-password"
            aria-describedby="token-help"
            required
            spellCheck={false}
          />
        </label>
        <div className="actions">
          <Submit pendingLabel="인증 중…">로그인</Submit>
        </div>
      </form>
      <ul className="instructions">
        <li>토큰 용도: 서버 API 인증</li>
        <li>공용 기기: 작업 후 로그아웃 필수</li>
      </ul>
    </section>
  );
}
