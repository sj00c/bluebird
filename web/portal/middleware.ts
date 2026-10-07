import { NextResponse, type NextRequest } from "next/server";

// 허용 메서드: 조회(GET/HEAD)와 이의 제기 접수(POST)만. 그 밖은 405.
const ALLOWED = new Set(["GET", "HEAD", "POST"]);

export function middleware(req: NextRequest) {
  if (!ALLOWED.has(req.method)) {
    return new NextResponse(null, { status: 405, headers: { Allow: "GET, HEAD, POST" } });
  }
  return NextResponse.next();
}

export const config = { matcher: "/:path*" };
