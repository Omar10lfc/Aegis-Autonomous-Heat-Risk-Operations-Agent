export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export interface JobAccepted {
  job_id: string;
  status: string;
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string | null;
  error: string | null;
  langsmith_url: string | null;
}

export interface Citation {
  endpoint: string;
  activity_id: string | null;
  label: string;
  field: string;
  value: number | null;
  units: string | null;
}

export interface HeatmapJob {
  label: string;
  analytic_type?: string;
  polygon_aoi: {
    type: string;
    features: Array<{
      geometry: { coordinates: number[][][] };
    }>;
  };
}

export interface Plan {
  brief?: string;
  analysis_layer?: string;
  heatmap_jobs: HeatmapJob[];
}

export interface AuditStats {
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  units?: string | null;
  analytic_type?: string | null;
}

export interface AuditCall {
  label: string;
  endpoint: string;
  activity_id: string | null;
  status: string;
  attempts: number;
  error: string | null;
  result?: {
    stats_data?: AuditStats;
  } | null;
}

export interface Report {
  job_id: string;
  markdown: string;
  citations: Citation[];
  plan: Plan | null;
  audit_trail: AuditCall[];
  langsmith_url: string | null;
  planner_model: string | null;
  fortyguard_mode: string | null;
  created_at: string;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function submitBrief(brief: string): Promise<JobAccepted> {
  const res = await fetch(`${BACKEND_URL}/brief`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brief }),
  });
  return handle<JobAccepted>(res);
}

export async function getStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BACKEND_URL}/status/${jobId}`, {
    cache: "no-store",
  });
  return handle<JobStatus>(res);
}

export async function getReport(jobId: string): Promise<Report> {
  const res = await fetch(`${BACKEND_URL}/report/${jobId}`, {
    cache: "no-store",
  });
  return handle<Report>(res);
}
