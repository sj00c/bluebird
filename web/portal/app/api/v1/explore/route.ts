import { NextResponse } from "next/server";
import { explore } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/v1/explore?q=... : 화면2와 같은 조회(pg_trgm). p95 측정 대상.
export async function GET(req: Request) {
  const q = (new URL(req.url).searchParams.get("q") ?? "").trim().slice(0, 200);
  if (q.length < 2) return NextResponse.json({ ok: false, detail: "q must be at least 2 characters" }, { status: 400 });
  const r = await explore(q);
  return NextResponse.json({ q, ...r });
}
