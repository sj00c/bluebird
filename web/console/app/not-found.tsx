import Link from "next/link";
import { getMe } from "@/lib/api";

export default async function NotFound() {
  const me = await getMe();
  const staff = me?.roles.some((role) =>
    ["reviewer", "expert", "auditor"].includes(role),
  );
  const href = staff ? "/" : me?.roles.includes("coder") ? "/coding" : "/login";
  return (
    <section className="card state-panel">
      <h1>자료 없음</h1>
      <ul className="instructions">
        <li>가능한 원인: 잘못된 주소 또는 운영 대상 제외</li>
        <li>현재 역할의 작업 공간에서 자료 재검색</li>
      </ul>
      <Link className="button" href={href}>
        {staff
          ? "검토 대기열로"
          : me?.roles.includes("coder")
            ? "독립 코딩으로"
            : "로그인으로"}
      </Link>
    </section>
  );
}
