"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// 화면 시안의 탭 5개. 카드 상세(/ideas/…)는 진단 카드 탭에 속한다.
const TABS: { href: string; label: string; match: (p: string) => boolean }[] = [
  { href: "/pool", label: "아이디어 풀", match: (p) => p.startsWith("/pool") },
  { href: "/", label: "진단 카드", match: (p) => p === "/" || p.startsWith("/ideas") },
  { href: "/timeliness", label: "시의성 재평가", match: (p) => p.startsWith("/timeliness") },
  { href: "/match", label: "공고 매칭", match: (p) => p.startsWith("/match") },
  { href: "/stats", label: "통계", match: (p) => p.startsWith("/stats") },
];

export function Nav() {
  const path = usePathname() ?? "/";
  return (
    <nav aria-label="주 메뉴">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} className={t.match(path) ? "on" : undefined}
              aria-current={t.match(path) ? "page" : undefined}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
