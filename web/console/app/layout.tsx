import type { Metadata } from "next";
import Link from "next/link";
import { getMe } from "@/lib/api";
import { logout } from "./actions";
import "./globals.css";

export const metadata: Metadata = {
  title: "파랑새 관리자 콘솔",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const me = await getMe();
  // 코더만인 사람은 큐·상세를 볼 수 없다(예측 원인을 보고 코딩하면 κ가 부풀려진다). API도 403.
  const isStaff = !!me && me.roles.some((r) => ["reviewer", "expert", "auditor"].includes(r));
  return (
    <html lang="ko">
      <body>
        <header className="top">
          <Link href="/" className="logo">파랑새 관리자 콘솔</Link>
          {me && <nav>
            {isStaff && <Link href="/">검토 대기</Link>}
            {me.roles.includes("coder") && <Link href="/coding">2인 코딩</Link>}
            {(me.roles.includes("reviewer") || me.roles.includes("auditor")) && <Link href="/objections">이의 처리</Link>}
          </nav>}
          {me && (
            <div className="right">
              {me.user} · {me.roles.join(", ")}
              <form action={logout} className="inline">
                <button type="submit" className="link">로그아웃</button>
              </form>
            </div>
          )}
        </header>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
