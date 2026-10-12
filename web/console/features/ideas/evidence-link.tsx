import type { ReactNode } from "react";
export function EvidenceLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  if (!/^https?:\/\//i.test(href)) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="lnk">
      {children}
      <span className="sr-only"> (새 창)</span> ↗
    </a>
  );
}
