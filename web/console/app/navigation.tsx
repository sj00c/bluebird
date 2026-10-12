"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Navigation({
  links,
}: {
  links: { href: string; label: string; index: string }[];
}) {
  const path = usePathname();
  return (
    <nav aria-label="운영 메뉴">
      {links.map((link) => {
        const active =
          link.href === "/"
            ? path === "/" || path.startsWith("/ideas/")
            : path.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={active ? "active" : ""}
            aria-current={active ? "page" : undefined}
          >
            <span aria-hidden="true">{link.index}</span>
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
