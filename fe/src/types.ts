export type JobStatus = 'pending' | 'running' | 'done' | 'failed'

export type Confidence = 'cao' | 'vừa'

export type MeasureKey =
  | 'disc_height_mm'
  | 'dhi'
  | 'disc_csf_ratio'
  | 'disc_vb_ratio'
  | 'disc_post_bulge_mm'
  | 'canal_ap_mm'
  | 'canal_csa_approx_mm2'
  | 'listhesis_mm'

export interface Suggestion {
  label: string
  label_vi: string
  measure: MeasureKey
  measure_vi: string
  value: number
  rule: '>=' | '<='
  threshold: number
  threshold_unit: 'gốc' | 'z'
  percentile: number
  confidence: Confidence
  sensitivity: number
  specificity: number
  ppv: number
}

export interface LevelAnalysis {
  level: string
  missing: 'disc' | 'mid_slices' | null
  measures: Partial<Record<MeasureKey, number>>
  suggestions: Suggestion[]
}

export interface AnalysisError {
  code: string
  message: string
}

export interface Analysis {
  qc: { ok: boolean; warnings: { code: string; message: string }[] } | null
  levels: LevelAnalysis[]
  lordosis_deg: number | null
  disclaimer: string | null
  error: AnalysisError | null
}

export interface JobResult {
  input_url: string
  segmentation_url: string
  labels_url: string
  labels_present: number[]
  analysis: Analysis | null
}

export interface JobError {
  code: string
  message: string
  log_tail?: string
}

export interface Job {
  job_id: string
  status: JobStatus
  queue_position: number | null
  input: { filename: string; size_bytes: number }
  options: { iso: boolean; step1_only: boolean }
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  result: JobResult | null
  error: JobError | null
}

export interface JobListItem {
  job_id: string
  status: JobStatus
  filename: string
  created_at: string
}

export interface JobList {
  items: JobListItem[]
  total: number
  limit: number
  offset: number
}

export interface CreatedJob {
  job_id: string
  status: JobStatus
  created_at: string
  links: { self: string }
}

export interface Health {
  status: string
  gpu_available: boolean
  queue: { pending: number; running: number }
  api_version: string
}

export type LabelGroup = 'cord' | 'canal' | 'vertebra' | 'disc'

export interface Label {
  value: number
  name: string
  group: LabelGroup
  color: string
}

export interface CreateJobInput {
  file: File
  iso: boolean
  step1_only: boolean
}
