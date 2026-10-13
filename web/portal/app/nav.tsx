"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// 아이디어 상세에서도 작업대 탐색 위치 유지
const TABS: {
  href: string;
  label: string;
  icon: string;
  match: (p: string) => boolean;
}[] = [
  {
    href: "/",
    label: "작업대",
    icon: "▦",
    match: (p) => p === "/" || p.startsWith("/ideas"),
  },
  {
    href: "/pool",
    label: "아이디어",
    icon: "▤",
    match: (p) => p.startsWith("/pool"),
  },
  {
    href: "/match",
    label: "공고 매칭",
    icon: "↗",
    match: (p) => p.startsWith("/match"),
  },
  {
    href: "/timeliness",
    label: "시의성",
    icon: "◷",
    match: (p) => p.startsWith("/timeliness"),
  },
  {
    href: "/stats",
    label: "공개 현황",
    icon: "≡",
    match: (p) => p.startsWith("/stats"),
  },
];

export function Nav() {
  const path = usePathname() ?? "/";
  return (
    <nav className="primary-nav" aria-label="주 메뉴">
      {TABS.map((t) => (
        <Link
          key={t.href}
          href={t.href}
          className={t.match(path) ? "on" : undefined}
          aria-current={t.match(path) ? "page" : undefined}
        >
          <span className="nav-symbol" aria-hidden="true">
            {t.icon}
          </span>
          <span>{t.label}</span>
        </Link>
      ))}
    </nav>
  );
}
