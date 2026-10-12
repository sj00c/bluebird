import Link from "next/link";
import { getMe } from "@/lib/api";

export default async function Forbidden() {
  const me = await getMe();
  const staff = me?.roles.some((role) =>
    ["reviewer", "expert", "auditor"].includes(role),
  );
  return (
    <section className="card state-panel">
      <p className="eyebrow">접근 제한</p>
      <h1>작업 권한 없음</h1>
      <ul className="instructions">
        <li>현재 역할에서 접근 불가</li>
        <li>독립 코더: 다른 코더 판단·시스템 예측 비공개</li>
        <li>권한 변경: 운영자에게 요청</li>
      </ul>
      <Link
        className="button"
        href={
          staff
            ? "/overview"
            : me?.roles.includes("coder")
              ? "/coding"
              : "/login"
        }
      >
        {staff
          ? "운영 개요로"
          : me?.roles.includes("coder")
            ? "독립 코딩으로"
            : "로그인으로"}
      </Link>
    </section>
  );
}
