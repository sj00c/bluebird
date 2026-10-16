import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { getMe } from "@/lib/api";
import { ROLES } from "@/lib/labels";
import { logout } from "./actions";
import { Navigation } from "./navigation";
import "./globals.css";

export const metadata: Metadata = {
  title: "파랑새 운영 콘솔",
  description: "검토 대기열, 분석 작성, 검토·승인 관리",
  robots: { index: false, follow: false },
};
export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  const me = await getMe();
  const isStaff =
    !!me &&
    me.roles.some((role) => ["reviewer", "expert", "auditor"].includes(role));
  const home = isStaff
    ? "/overview"
    : me?.roles.includes("coder")
      ? "/coding"
      : "/login";
  const links = [
    ...(isStaff
      ? [
          { href: "/overview", label: "운영 개요", index: "01" },
          { href: "/", label: "검토 대기열", index: "02" },
        ]
      : []),
    ...(me?.roles.includes("coder")
      ? [{ href: "/coding", label: "독립 코딩", index: "03" }]
      : []),
  ];
  return (
    <html lang="ko">
      <head>
        <link rel="stylesheet" href="/fonts/pretendard-1.3.9/pretendard.css" />
      </head>
      <body>
        <a className="skip" href="#main">
          본문으로 바로 가기
        </a>
        <div className={me ? "shell" : "shell anonymous"}>
          <aside className="sidebar">
            <Link href={home} className="logo">
              <span className="brand-mark" aria-hidden="true">
                파
              </span>
              <span>
                파랑새<small>운영 콘솔</small>
              </span>
            </Link>
            {me && <Navigation links={links} />}
          </aside>
          <div className="main-shell">
            <header className="top">
              <span className="workspace-label">파랑새 / 운영 콘솔</span>
              {me ? (
                <div className="account">
                  <span>
                    <b>{me.user}</b>
                    <small>
                      {me.roles.map((role) => ROLES[role] ?? role).join(" · ")}
                    </small>
                  </span>
                  <form action={logout}>
                    <button type="submit" className="sub small">
                      로그아웃
                    </button>
                  </form>
                </div>
              ) : (
                <span className="muted">인증된 운영자 전용</span>
              )}
            </header>
            <main id="main" className="wrap">
              {children}
            </main>
            <footer className="footer">저장 → 검토·승인</footer>
          </div>
        </div>
      </body>
    </html>
  );
}
