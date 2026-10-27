/** Types alignés sur les schémas Pydantic de l'API (/api/v1). */

export type OpportunityType = "internship" | "masters_scholarship";
export type Eligibility = "eligible" | "ineligible" | "unknown";
export type DeadlineStatus = "confirmed" | "unverified" | "unknown";
export type ApplicationStatus =
  | "to_explore"
  | "to_prepare"
  | "preparing"
  | "submitted"
  | "selection"
  | "accepted"
  | "rejected"
  | "withdrawn";
export type TaskStatus = "todo" | "in_progress" | "done" | "cancelled";

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "to_explore",
  "to_prepare",
  "preparing",
  "submitted",
  "selection",
  "accepted",
  "rejected",
  "withdrawn",
];
export const SUBMITTED_STATUSES: ApplicationStatus[] = ["submitted", "selection", "accepted"];

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  timezone: string;
  locale: string;
  last_seen_at: string | null;
  previous_seen_at: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface MatchSummary {
  eligibility: Eligibility;
  score: number;
  confidence: number;
  computed_at: string;
}

export interface OpportunityListItem {
  id: string;
  type: OpportunityType;
  title: string;
  organization: string;
  countries: string[];
  location: string | null;
  remote: boolean | null;
  fields: string[];
  study_levels: string[];
  funding_type: "full" | "partial" | "none" | "unknown";
  deadline_at: string | null;
  deadline_status: DeadlineStatus;
  status: "open" | "closed" | "unknown";
  official_url: string;
  verification_status: string;
  first_seen_at: string;
  last_verified_at: string | null;
  is_favorite: boolean;
  application_id: string | null;
  application_status: ApplicationStatus | null;
  match: MatchSummary | null;
}

export interface MatchListItem extends OpportunityListItem {
  satisfied: string[];
  unsatisfied: string[];
  unknown: string[];
  to_complete: string[];
  confidence_label: string | null;
}

export interface Criterion {
  key: string;
  label: string;
  weight: number;
  effective_weight: number;
  status: "met" | "partial" | "unmet" | "unknown" | "not_applicable";
  value: number;
  known_fraction: number;
  points: number;
  details: string[];
}

export interface EligibilityCheck {
  key: string;
  label: string;
  status: "satisfied" | "failed" | "unknown";
  detail: string;
}

export interface MatchExplanation {
  engine_version: string;
  eligibility: { status: Eligibility; checks: EligibilityCheck[]; notes: string[] };
  criteria: Criterion[];
  satisfied: string[];
  unsatisfied: string[];
  unknown: string[];
  partial: string[];
  to_complete: string[];
  score: number;
  confidence: number;
  confidence_label: string;
  reliable: boolean;
  disclaimer: string;
}

export interface SourceRef {
  source_key: string;
  source_name: string;
  source_url: string;
  first_seen_at: string;
  last_seen_at: string;
}

export interface OpportunityDetail extends OpportunityListItem {
  description: string | null;
  eligibility_criteria: string | null;
  eligible_nationalities: string[] | null;
  required_languages: { code: string; level?: string }[];
  required_documents: string[];
  funding_amount: string | null;
  tuition_covered: boolean | null;
  stipend: string | null;
  benefits: string | null;
  duration_months: number | null;
  opens_at: string | null;
  deadline_timezone: string | null;
  tags: string[];
  last_seen_at: string;
  content_changed_at: string | null;
  significant_change_at: string | null;
  significant_change_fields: string[];
  sources: SourceRef[];
  match_detail: MatchExplanation | null;
}

export interface Facets {
  countries: string[];
  fields: string[];
  organizations: string[];
  types: string[];
}

export interface LanguageItem {
  code: string;
  level: string;
}
export interface ExperienceItem {
  title: string;
  organization?: string | null;
  location?: string | null;
  start?: string | null;
  end?: string | null;
  current?: boolean;
  description?: string | null;
  skills?: string[];
}
export interface ProjectItem {
  name: string;
  description?: string | null;
  url?: string | null;
  skills?: string[];
}
export interface LeadershipItem {
  role: string;
  organization?: string | null;
  start?: string | null;
  end?: string | null;
  description?: string | null;
}

export interface Profile {
  full_name: string | null;
  contact_email: string | null;
  phone: string | null;
  city: string | null;
  country_of_residence: string | null;
  nationalities: string[];
  headline: string | null;
  summary: string | null;
  study_level: string | null;
  current_degree: string | null;
  institution: string | null;
  field_of_study: string | null;
  academic_year: string | null;
  expected_graduation: string | null;
  academic_results: string | null;
  skills: string[];
  experiences: ExperienceItem[];
  projects: ProjectItem[];
  leadership: LeadershipItem[];
  languages: LanguageItem[];
  target_countries: string[];
  internship_fields: string[];
  master_fields: string[];
  funding_preference: string | null;
  program_types: string[];
  internship_duration_min_months: number | null;
  internship_duration_max_months: number | null;
  accepts_remote: boolean | null;
  version: number;
  updated_at: string;
  completeness: number;
  missing_fields: string[];
}

export interface CvExtraction {
  text_length: number;
  pages: number;
  suggestions: {
    contact_email?: string;
    phone?: string;
    full_name?: string;
    skills?: string[];
    languages?: { code: string; level: string | null }[];
    links?: string[];
    study_level_mentioned?: string;
  };
  evidence: Record<string, string>;
  warnings: string[];
}

export interface Urgency {
  level: "expiree" | "critique" | "haute" | "moyenne" | "basse";
  score: number;
  reasons: string[];
  days_left: number | null;
}

export interface LinkedDocument {
  id: string;
  title: string;
  doc_type: string;
  version: number;
  role: string | null;
  added_at: string;
}

export interface Application {
  id: string;
  opportunity: {
    id: string;
    type: OpportunityType;
    title: string;
    organization: string;
    official_url: string;
    deadline_at: string | null;
    deadline_status: DeadlineStatus;
    status: string;
    required_documents: string[];
    countries: string[];
  };
  status: ApplicationStatus;
  deadline_at: string | null;
  submitted_at: string | null;
  submission_confirmed_at: string | null;
  notes: string | null;
  contact_name: string | null;
  contact_email: string | null;
  next_action: string | null;
  next_action_at: string | null;
  follow_up_at: string | null;
  response_notes: string | null;
  response_received_at: string | null;
  estimated_prep_hours: number | null;
  created_at: string;
  updated_at: string;
  urgency: Urgency | null;
  eligibility: Eligibility | null;
  score: number | null;
  documents: LinkedDocument[];
  open_tasks: number;
}

export interface ApplicationEvent {
  id: string;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Task {
  id: string;
  application_id: string | null;
  title: string;
  description: string | null;
  due_at: string | null;
  status: TaskStatus;
  completed_at: string | null;
  created_at: string;
  overdue: boolean;
  application_title: string | null;
}

export interface DocumentItem {
  id: string;
  group_id: string;
  version: number;
  doc_type: string;
  title: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
  application_ids: string[];
}

export interface NotificationPrefs {
  email: string | null;
  enabled: boolean;
  digest_frequency: "daily" | "weekly" | "never";
  digest_weekday: number;
  digest_hour: number;
  notify_new_matches: boolean;
  notify_deadlines: boolean;
  notify_tasks: boolean;
  notify_changes: boolean;
  notify_ingestion_errors: boolean;
  min_score: number;
  max_items: number;
  deadline_reminder_days: number[];
  last_digest_sent_at: string | null;
  email_mode: "resend" | "simulation";
  effective_recipient: string | null;
}

export interface NotificationLog {
  id: string;
  kind: string;
  dedup_key: string;
  recipient: string;
  subject: string;
  status: string;
  provider: string;
  provider_message_id: string | null;
  attempts: number;
  last_error: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  sent_at: string | null;
}

export interface NotificationPreview {
  kind: string;
  subject: string;
  html: string;
  text: string;
  items: number;
  note: string | null;
}

export interface Dashboard {
  generated_at: string;
  last_visit_at: string | null;
  opportunities_total: number;
  opportunities_by_type: Record<string, number>;
  new_since_last_visit: number;
  eligible: number;
  eligibility_unknown: number;
  ineligible: number;
  applications_by_status: Record<string, number>;
  applications_in_progress: number;
  applications_submitted: number;
  deadlines_7_days: number;
  deadlines_30_days: number;
  upcoming: {
    application_id: string;
    opportunity_id: string;
    title: string;
    organization: string;
    deadline_at: string;
    deadline_status: DeadlineStatus;
    status: ApplicationStatus;
    urgency: Urgency | null;
  }[];
  overdue_tasks: { id: string; title: string; due_at: string | null; application_id: string | null }[];
  favorites: number;
  latest_runs: { id: string; source: string | null; status: string; started_at: string; created: number; updated: number; errors: number }[];
  sources: { key: string; name: string; enabled: boolean; verification_status: string; last_success_at: string | null; consecutive_failures: number }[];
  latest_emails: { id: string; kind: string; subject: string; status: string; created_at: string }[];
  recent_errors: { type: string; source: string | null; message: string; at: string }[];
}

export interface CalendarEvent {
  id: string;
  kind: "deadline" | "favorite_deadline" | "task" | "next_action" | "follow_up";
  title: string;
  subtitle: string | null;
  at: string;
  deadline_status: DeadlineStatus | null;
  application_id: string | null;
  opportunity_id: string | null;
  status: string | null;
  urgency: string | null;
  overdue: boolean;
}

export interface Source {
  id: string;
  key: string;
  name: string;
  connector: string;
  base_url: string;
  description: string | null;
  terms_notes: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
  rate_limit_seconds: number;
  max_items: number;
  verification_status: string;
  last_run_at: string | null;
  last_success_at: string | null;
  last_tested_at: string | null;
  consecutive_failures: number;
  last_error: string | null;
  opportunities_count: number;
}

export interface IngestionRun {
  id: string;
  source_id: string | null;
  job_name: string;
  triggered_by: string;
  dry_run: boolean;
  status: string;
  started_at: string;
  finished_at: string | null;
  items_fetched: number;
  items_created: number;
  items_updated: number;
  items_unchanged: number;
  items_skipped: number;
  errors_count: number;
  details: { errors?: { item: string; error: string }[]; fatal?: string | null; closed?: number };
}

export interface SourceTestResult {
  source_key: string;
  ok: boolean;
  items_found: number;
  sample: { title: string; organization: string; type: string; official_url: string; countries: string[]; deadline_status: string }[];
  errors: string[];
  verification_status: string;
  duration_ms: number;
}

export interface AssistResult {
  enabled: boolean;
  kind: string;
  draft: string | null;
  missing_information: string[];
  used_fields: string[];
  warning: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: unknown };
}
