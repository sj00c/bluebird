import type { OBJECTION_KINDS } from "./input";

export type IdeaRow = {
  id: string;
  source_id: string;
  source_name: string;
  license: string;
  contest_name: string;
  host_org: string;
  year: number | null;
  award: string | null;
  title: string;
  body: string | null;
  used_data: string[];
  category: string | null;
  source_url: string | null;
  card_kind: string | null;
  problem: string | null;
  solution: string | null;
  trace_status: string | null;
  external_search: string | null;
};
export type PoolFilter = {
  q?: string;
  year?: number;
  source?: string;
  verified?: boolean;
  page: number;
};
export type DiagnosisRow = {
  cause: string;
  secondary: string | null;
  rationale: string | null;
  evidence_ids: string[];
};

export type ChangeRow = {
  id: string;
  kind: string;
  tier: string | null;
  occurred_at: string | null;
  registered_at: string | null;
  title: string;
  url: string | null;
  what_changed: string[];
  how_now: string | null;
  evidence_ids: string[];
};

export type TimelinessRow = {
  as_of: string | null;
  tech: number | null;
  data: number | null;
  regulation: number | null;
  policy: number | null;
  n_scored: number | null;
  s: number | null;
  verdict: string;
  resolve_condition: string | null;
  evidence_ids: string[];
};

export type EvidenceRow = {
  id: string;
  kind: string | null;
  url: string | null;
  title: string | null;
  excerpt: string | null;
};
export type TopRow = {
  rank: number;
  idea_id: string;
  title: string;
  year: number | null;
  contest_name: string;
  s: number | null;
  verdict: string | null;
  cause: string | null;
  change_title: string | null;
  change_kind: string | null;
};
export type ExploreIdea = {
  id: string;
  title: string;
  year: number | null;
  contest_name: string;
  award: string | null;
  score: number;
  cause: string | null;
  verdict: string | null;
  s: number | null;
};
export type ExploreAnnouncement = {
  id: string;
  title: string;
  org: string | null;
  apply_to: string | null;
  url: string;
};
export type ObjectionKind = (typeof OBJECTION_KINDS)[number];
export type TimelinessListRow = TimelinessRow & {
  idea_id: string;
  title: string;
  year: number | null;
  contest_name: string;
  cause: string | null;
};
export type AnnouncementMatchRow = {
  id: string;
  title: string;
  org: string | null;
  apply_to: string | null;
  url: string;
  similarity: number | null;
};
export type PoolOverview = {
  ideas: number;
  sources: number;
  traced: number;
  externalSearched: number;
  verified: number;
  revival: number;
  changes: number;
  scored: number;
  announcements: number;
  causes: { cause: string; n: number }[];
  verdicts: { verdict: string; n: number }[];
};
export type SourceStat = {
  id: string;
  name: string;
  license: string;
  url: string;
  ideas: number;
  with_body: number;
  y_min: number | null;
  y_max: number | null;
};
