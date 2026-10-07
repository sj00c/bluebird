import Link from "next/link";

export default function NotFound() {
  return (
    <>
      <h1>찾을 수 없습니다</h1>
      <p className="muted">없는 아이디어이거나 퇴역한 행입니다.</p>
      <p><Link href="/">검토 대기로</Link></p>
    </>
  );
}
