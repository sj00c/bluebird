import { NextResponse } from "next/server";
import { insertObjection, OBJECTION_KINDS, type ObjectionKind } from "@/lib/db";

export const dynamic = "force-dynamic";

const ID_RE = /^ID-[0-9]{4}-[0-9a-f]{10}$/;

export async function POST(req: Request) {
  const isJson = (req.headers.get("content-type") ?? "").includes("application/json");
  let ideaId = "";
  let kind = "";
  let body = "";
  try {
    if (isJson) {
      const j = (await req.json()) as Record<string, unknown>;
      ideaId = typeof j.idea_id === "string" ? j.idea_id : "";
      kind = typeof j.kind === "string" ? j.kind : "";
      body = typeof j.body === "string" ? j.body : "";
    } else {
      const f = await req.formData();
      const v = (k: string) => {
        const x = f.get(k);
        return typeof x === "string" ? x : "";
      };
      ideaId = v("idea_id");
      kind = v("kind");
      body = v("body");
    }
  } catch {
    return respond(isJson, ideaId, 400, "bad_request");
  }
  body = body.trim();
  if (!ID_RE.test(ideaId)) return respond(isJson, "", 400, "bad_request");
  if (!(OBJECTION_KINDS as readonly string[]).includes(kind) || body.length < 1 || body.length > 2000) {
    return respond(isJson, ideaId, 400, "bad_request");
  }
  let found: boolean;
  try {
    found = await insertObjection({ ideaId, kind: kind as ObjectionKind, body });
  } catch {
    return respond(isJson, ideaId, 500, "server_error");
  }
  if (!found) return respond(isJson, ideaId, 404, "not_found");
  if (isJson) return NextResponse.json({ ok: true }, { status: 201 });
  return seeOther(`/ideas/${ideaId}?objection=ok#objection`);
}

function respond(isJson: boolean, ideaId: string, status: number, detail: string) {
  if (isJson || !ID_RE.test(ideaId)) {
    return NextResponse.json({ ok: false, detail }, { status });
  }
  return seeOther(`/ideas/${ideaId}?objection=error#objection`);
}

// 상대 경로 Location: 컨테이너 안 주소(0.0.0.0:3000)가 아니라 브라우저가 연 nginx 주소 기준으로 이동한다.
function seeOther(location: string) {
  return new NextResponse(null, { status: 303, headers: { Location: location } });
}
