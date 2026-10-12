import { NextRequest, NextResponse } from "next/server";
import { cleanQuery, PAGE_SIZE, parsePage } from "@/lib/input";
import { listIdeas } from "@/lib/ideas";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const q = cleanQuery(sp.get("q")) || undefined;
  const yearRaw = sp.get("year") ?? "";
  const year = /^\d{4}$/.test(yearRaw) ? Number(yearRaw) : undefined;
  const page = parsePage(sp.get("page"));
  const { total, rows } = await listIdeas({ q, year, page });
  return NextResponse.json({ total, page, page_size: PAGE_SIZE, items: rows });
}
