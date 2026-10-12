import Link from "next/link";

export function PoolFilters({
  query,
  year,
  source,
  verified,
  sources,
}: {
  query: string;
  year?: number;
  source?: string;
  verified: boolean;
  sources: { id: string; name: string }[];
}) {
  return (
    <section className="card" aria-label="아이디어 검색 필터">
      <form className="filter-form" action="/pool">
        <label className="query-field" htmlFor="pool-q">
          제목 검색
          <input
            id="pool-q"
            name="q"
            defaultValue={query}
            maxLength={200}
            placeholder="제목 키워드"
          />
        </label>
        <label htmlFor="pool-source">
          출처
          <select id="pool-source" name="source" defaultValue={source ?? ""}>
            <option value="">모든 출처</option>
            {sources.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="pool-year">
          제출 연도
          <input
            id="pool-year"
            name="year"
            defaultValue={year ?? ""}
            inputMode="numeric"
            pattern="[0-9]{4}"
            maxLength={4}
            placeholder="예: 2020"
          />
        </label>
        <label htmlFor="pool-verified">
          진단 검증
          <select
            id="pool-verified"
            name="verified"
            defaultValue={verified ? "1" : ""}
          >
            <option value="">공개 원본 전체</option>
            <option value="1">검증된 진단만</option>
          </select>
        </label>
        <button type="submit">검색</button>
        <Link className="reset-link" href="/pool">
          초기화
        </Link>
      </form>
    </section>
  );
}
