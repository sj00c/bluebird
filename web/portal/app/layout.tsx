import type { Metadata } from "next";
import Link from "next/link";
import { poolStats } from "@/lib/db";
import "./globals.css";

export const metadata: Metadata = {
  title: "파랑새 · 공모전 아이디어 풀 진단·재발굴",
  description: "공모전 수상·공개 아이디어를 구조화하고 다시 깨우는 공공 서비스",
};

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const stats = await poolStats();
  return (
    <html lang="ko">
      <body>
        <header className="top">
          <Link href="/pool" className="logo">
            파랑새<span>Bluebird · 공모전 아이디어 풀 진단·재발굴</span>
          </Link>
          <nav>
            <Link href="/pool">아이디어 풀</Link>
          </nav>
          <div className="right">
            풀 {stats.ideas.toLocaleString("ko-KR")}건 · 출처 {stats.sources}종
            {stats.snapshotAt && ` · 갱신 ${stats.snapshotAt.toISOString().slice(0, 10)}`}
          </div>
        </header>
        <main className="wrap">{children}</main>
        <footer className="foot">
          공공데이터포털 등 공개 데이터 기반 · 아이디어 단위 익명 처리 · 원문은 변형하지 않음 · 파랑새 시험 운영
        </footer>
      </body>
    </html>
  );
}
