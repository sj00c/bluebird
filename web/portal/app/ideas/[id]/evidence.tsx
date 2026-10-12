import type { EvidenceRow } from "@/lib/types";

export function Evidence({
  ids,
  byId,
}: {
  ids: string[];
  byId: ReadonlyMap<string, EvidenceRow>;
}) {
  return (
    <>
      {ids.map((id) => {
        const evidence = byId.get(id);
        if (!evidence) return null;
        return (
          <div className="evidence-item" key={id}>
            {evidence.url ? (
              <a
                className="link"
                href={evidence.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {evidence.title || evidence.url}
              </a>
            ) : (
              <span>{evidence.title}</span>
            )}
            {evidence.excerpt && (
              <details className="more">
                <summary>근거 발췌</summary>
                <blockquote className="quote">{evidence.excerpt}</blockquote>
              </details>
            )}
          </div>
        );
      })}
    </>
  );
}
