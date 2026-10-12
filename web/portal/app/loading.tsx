export default function Loading() {
  return (
    <section
      className="card state-panel"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <p className="eyebrow">공개 데이터</p>
      <h1>조회 중</h1>
      <div aria-hidden="true">
        <div className="loading-line" />
        <div className="loading-line short" />
        <div className="loading-line" />
      </div>
    </section>
  );
}
