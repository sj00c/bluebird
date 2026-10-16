export type Me = { user: string; roles: string[] };

export type Overview = {
  counts: Record<string, number>;
  sources: {
    id: string;
    name: string;
    public_ok: boolean;
    export_grade: string | null;
    ideas: number;
    check_status: string | null;
    checked_at: string | null;
  }[];
  runs: {
    stage: string;
    status: string;
    started_at: string;
    finished_at: string | null;
  }[];
  checks: { source_id: string; status: string; checked_at: string }[];
};

export type QueueItem = {
  idea_id: string;
  title: string;
  year: number | null;
  source_id: string;
  cause: string | null;
  stage: string;
  s: number | null;
  verdict: string | null;
};
export type Queue = {
  items: QueueItem[];
  counts: Record<string, number>;
  total: number;
  limit: number;
  offset: number;
};

export type CodingItem = {
  idea_id: string;
  title: string;
  body: string | null;
  card_problem: string | null;
  missing_data: ({ name: string } | string)[] | null;
  my_code: string | null;
};
export type Coding = { sample_id: string | null; items: CodingItem[] };

export type Change = {
  id: string;
  kind: string;
  title: string;
  url: string | null;
  occurred_at: string | null;
  verify_status: string | null;
};
export type Changes = { items: Change[] };

export type Detail = {
  idea: {
    id: string;
    title: string;
    body: string | null;
    year: number | null;
    award: string | null;
    contest: string | null;
    source_id: string;
    source_url: string | null;
    public_ok: boolean;
    withheld_at: string | null;
  };
  card: {
    card_kind: string | null;
    problem: string | null;
    solution: string | null;
    missing_data: { name: string; excerpt: string | null }[];
    extractor: string | null;
  } | null;
  trace: {
    status: string | null;
    profile_version: string | null;
    checks: {
      item: string;
      result: string;
      detail: Record<string, unknown> | null;
    }[];
  } | null;
  diagnosis: {
    cause: string;
    secondary: string | null;
    rationale: string | null;
    extractor: string | null;
    decided_by: string | null;
    evidence: { url: string; excerpt: string | null }[];
  } | null;
  matches: {
    id: number | string;
    change_id: number | string;
    kind: string;
    title: string;
    url: string | null;
    occurred_at: string | null;
    verify_status: string | null;
    llm_verdict: string | null;
    status: string | null;
    what_changed: string[];
    how_now: string | null;
    eligible: boolean;
  }[];
  timeliness: {
    as_of: string | null;
    tech: number | null;
    data: number | null;
    regulation: number | null;
    policy: number | null;
    n_scored: number | null;
    s: number | null;
    verdict: string | null;
    resolve_condition: string | null;
    scored_by: string | null;
    evidence: Partial<
      Record<"tech" | "data" | "regulation" | "policy", string>
    >;
  } | null;
  stage: Record<string, boolean>;
  reviews: {
    round: string;
    reviewer: string;
    decision: string;
    code: string | null;
    note: string | null;
    created_at: string;
  }[];
};
