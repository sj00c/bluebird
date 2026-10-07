import { NextResponse } from "next/server";
import { getIdea } from "@/lib/db";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const idea = await getIdea(id);
  if (!idea) return NextResponse.json({ error: "not_found" }, { status: 404 });
  return NextResponse.json(idea);
}
