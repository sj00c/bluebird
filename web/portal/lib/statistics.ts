import "server-only";
import { pool } from "./connection";
import type { PoolOverview, SourceStat } from "./types";

export async function poolOverview(): Promise<PoolOverview> {
  const [a, c, v] = await Promise.all([
    pool.query<Record<string, string>>(
      `SELECT (SELECT count(*) FROM publish.idea) AS ideas,
              (SELECT count(*) FROM publish.source) AS sources,
              (SELECT count(*) FROM publish.idea WHERE trace_status IS NOT NULL AND trace_status <> 'pending') AS traced,
              (SELECT count(*) FROM publish.idea WHERE external_search = 'done') AS external_searched,
              (SELECT count(*) FROM publish.diagnosis) AS verified,
              (SELECT count(*) FROM publish.timeliness WHERE s >= 4.0) AS revival,
              (SELECT count(DISTINCT idea_id) FROM publish.change) AS changes,
              (SELECT count(*) FROM publish.timeliness) AS scored,
              (SELECT count(*) FROM publish.announcement) AS announcements`,
    ),
    pool.query<{ cause: string; n: number }>(
      `SELECT cause, count(*)::int AS n FROM publish.diagnosis GROUP BY cause ORDER BY n DESC, cause`,
    ),
    pool.query<{ verdict: string; n: number }>(
      `SELECT verdict, count(*)::int AS n FROM publish.timeliness GROUP BY verdict ORDER BY n DESC`,
    ),
  ]);
  const r = a.rows[0];
  return {
    ideas: Number(r.ideas),
    sources: Number(r.sources),
    traced: Number(r.traced),
    externalSearched: Number(r.external_searched),
    verified: Number(r.verified),
    revival: Number(r.revival),
    changes: Number(r.changes),
    scored: Number(r.scored),
    announcements: Number(r.announcements),
    causes: c.rows,
    verdicts: v.rows,
  };
}
export async function sourceStats(): Promise<SourceStat[]> {
  const r = await pool.query<SourceStat>(
    `SELECT s.id, s.name, s.license, s.url, count(i.id)::int AS ideas,
            count(i.id) FILTER (WHERE coalesce(btrim(i.body), '') <> '')::int AS with_body,
            min(i.year) AS y_min, max(i.year) AS y_max
       FROM publish.source s LEFT JOIN publish.idea i ON i.source_id = s.id
      GROUP BY s.id ORDER BY ideas DESC`,
  );
  return r.rows;
}

export async function yearStats(): Promise<{ year: number; n: number }[]> {
  const r = await pool.query<{ year: number; n: number }>(
    `SELECT year, count(*)::int AS n FROM publish.idea WHERE year IS NOT NULL GROUP BY year ORDER BY year`,
  );
  return r.rows;
}

export async function cardKindStats(): Promise<
  { card_kind: string; n: number }[]
> {
  const r = await pool.query<{ card_kind: string; n: number }>(
    `SELECT coalesce(card_kind, '-') AS card_kind, count(*)::int AS n FROM publish.idea GROUP BY 1 ORDER BY n DESC`,
  );
  return r.rows;
}
