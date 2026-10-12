import "server-only";
import { pool } from "./connection";
import type {
  ExploreIdea,
  ExploreAnnouncement,
  AnnouncementMatchRow,
} from "./types";

export const EXPLORE_LIMIT = 50;
export async function explore(q: string): Promise<{
  ideas: ExploreIdea[];
  causes: { cause: string; n: number }[];
  announcements: ExploreAnnouncement[];
}> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN READ ONLY");
    await client.query("SET LOCAL pg_trgm.word_similarity_threshold = 0.3");
    await client.query("SET LOCAL statement_timeout = '1s'");
    const ideas = await client.query<ExploreIdea>(
      `WITH hit AS (
         SELECT i.id, i.title, i.year, i.contest_name, i.award,
                greatest(word_similarity($1, i.title), 0.7 * word_similarity($1, coalesce(i.body, ''))) AS score
           FROM publish.idea i
          WHERE $1 <% i.title OR $1 <% i.body
          ORDER BY score DESC, i.id
          LIMIT ${EXPLORE_LIMIT})
       SELECT h.id, h.title, h.year, h.contest_name, h.award, round(h.score::numeric, 2)::float AS score,
              d.cause, t.verdict, t.s
         FROM hit h
         LEFT JOIN publish.diagnosis d ON d.idea_id = h.id
         LEFT JOIN publish.timeliness t ON t.idea_id = h.id
        ORDER BY h.score DESC, h.id`,
      [q],
    );
    const ann = await client.query<ExploreAnnouncement>(
      `SELECT id, title, org, apply_to::text AS apply_to, url
         FROM publish.announcement
        WHERE $1 <% title
        ORDER BY word_similarity($1, title) DESC, id
        LIMIT 10`,
      [q],
    );
    await client.query("COMMIT");
    const counts = new Map<string, number>();
    for (const r of ideas.rows)
      if (r.cause) counts.set(r.cause, (counts.get(r.cause) ?? 0) + 1);
    const causes = [...counts]
      .map(([cause, n]) => ({ cause, n }))
      .sort((a, b) => b.n - a.n);
    return { ideas: ideas.rows, causes, announcements: ann.rows };
  } catch (e) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw e;
  } finally {
    client.release();
  }
}
// ---------------------------------------------------------------- 카드 상세 보조: 비슷한 아이디어 수·관련 공고
// 제목 trigram 유사도(0.3 이상). 같은 아이디어는 뺀다. 결과는 공고 매칭 화면(/match?q=제목)과 같은 기준이 아니라
// 제목끼리의 비교라서 "비슷한 제목"으로만 표시한다.
export async function similarCount(
  id: string,
  title: string,
): Promise<number | null> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN READ ONLY");
    await client.query("SET LOCAL pg_trgm.similarity_threshold = 0.3");
    await client.query("SET LOCAL statement_timeout = '1s'");
    const r = await client.query<{ n: number }>(
      `SELECT count(*)::int AS n FROM publish.idea WHERE title % $1 AND id <> $2`,
      [title, id],
    );
    await client.query("COMMIT");
    return r.rows[0].n;
  } catch {
    await client.query("ROLLBACK").catch(() => undefined);
    return null;
  } finally {
    client.release();
  }
}
export async function announcementMatches(
  ideaId: string,
): Promise<AnnouncementMatchRow[]> {
  const r = await pool.query<AnnouncementMatchRow>(
    `SELECT a.id, a.title, a.org, a.apply_to::text AS apply_to, a.url, m.similarity
       FROM publish.announcement_match m JOIN publish.announcement a ON a.id = m.announcement_id
      WHERE m.idea_id = $1
      ORDER BY m.rank`,
    [ideaId],
  );
  return r.rows;
}

export async function recentAnnouncements(
  limit = 8,
): Promise<ExploreAnnouncement[]> {
  const r = await pool.query<ExploreAnnouncement>(
    `SELECT id, title, org, apply_to::text AS apply_to, url
       FROM publish.announcement
      ORDER BY apply_to DESC NULLS LAST, id
      LIMIT $1`,
    [limit],
  );
  return r.rows;
}
