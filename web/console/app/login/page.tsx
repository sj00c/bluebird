import { login } from "../actions";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return (
    <div className="card" style={{ maxWidth: 480, margin: "40px auto" }}>
      <h1>로그인</h1>
      {error && <div className="msg err">{error}</div>}
      <form action={login} className="stack">
        <label>
          접근 토큰
          <input type="password" name="token" autoComplete="current-password" required />
        </label>
        <div className="actions"><button type="submit">로그인</button></div>
      </form>
    </div>
  );
}
