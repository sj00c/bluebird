import "server-only";
import { pool } from "./connection";
import type { ObjectionKind } from "./types";

// bb_portal은 inbox를 SELECT할 수 없으므로 RETURNING 없이 INSERT만 한다.
// 아이디어가 없으면 false.
export async function insertObjection(o: {
  ideaId: string;
  kind: ObjectionKind;
  body: string;
}): Promise<boolean> {
  const exists = await pool.query(`SELECT 1 FROM publish.idea WHERE id = $1`, [
    o.ideaId,
  ]);
  if (exists.rowCount === 0) return false;
  await pool.query(
    `INSERT INTO inbox.objection (idea_id, kind, body) VALUES ($1, $2, $3)`,
    [o.ideaId, o.kind, o.body],
  );
  return true;
}
