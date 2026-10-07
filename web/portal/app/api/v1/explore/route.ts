import { NextResponse } from "next/server";
import { cleanQuery, explore } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/v1/explore?q=... : 화면2와 같은 조회(pg_trgm). p95 측정 대상.
export async function GET(req: Request) {
  const q = cleanQuery(new URL(req.url).searchParams.get("q"));
  if (q.length < 2) return NextResponse.json({ ok: false, detail: "q must be at least 2 characters" }, { status: 400 });
  try {
    const r = await explore(q);
    return NextResponse.json({ q, ...r });
  } catch (e) {
    // statement_timeout(57014): 과부하로 보고 잠시 뒤 다시 시도하게 한다. 그 밖의 오류는 그대로 500.
    if ((e as { code?: string }).code === "57014")
      return NextResponse.json({ ok: false, detail: "busy, retry later" }, { status: 503, headers: { "Retry-After": "5" } });
    throw e;
  }
}
