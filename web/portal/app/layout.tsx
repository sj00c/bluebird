import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { DashboardAtmosphere } from "./dashboard-atmosphere";
import { Nav } from "./nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "파랑새 · 공공 아이디어 워크스페이스",
  description:
    "공개 아이디어 검색, 검증 근거 조회, 주제·공고 매칭 및 시의성 평가.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link rel="stylesheet" href="/fonts/pretendard-1.3.9/pretendard.css" />
      </head>
      <body>
        <DashboardAtmosphere />
        <div className="app-shell">
          <a className="skip-link" href="#main-content">
            본문으로 바로가기
          </a>
          <aside className="sidebar">
            <Link href="/" className="logo" aria-label="파랑새 아이디어 작업대">
              <span className="brand-symbol" aria-hidden="true">
                B
              </span>
              <span className="brand-name">파랑새</span>
            </Link>
            <Nav />
            <div className="sidebar-status">
              <span>
                공개
                <br />
                시험 운영
              </span>
            </div>
          </aside>
          <div className="workspace">
            <header className="utility-bar">
              <span>공공 아이디어 워크스페이스</span>
              <Link href="/stats">
                출처·공개 현황 <span aria-hidden="true">↗</span>
              </Link>
            </header>
            <main id="main-content" className="wrap" tabIndex={-1}>
              {children}
            </main>
            <footer className="foot">
              <span>파랑새 · 공개 원본 / 검증 분석</span>
              <Link href="/stats">데이터 출처</Link>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
