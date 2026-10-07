import type { Metadata } from "next";
import Link from "next/link";
import { getMe } from "@/lib/api";
import { logout } from "./actions";
import "./globals.css";

export const metadata: Metadata = {
  title: "파랑새 관리자 콘솔 (업무망 전용)",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const me = await getMe();
  return (
    <html lang="ko">
      <body>
        <header className="top">
          <Link href="/" className="logo">파랑새 관리자 콘솔 (업무망 전용)</Link>
          <nav>
            <Link href="/">검토 대기</Link>
            <Link href="/coding">2인 코딩</Link>
            <Link href="/objections">이의 처리</Link>
          </nav>
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
