import type {
  Analysis,
  CreatedJob,
  Health,
  Job,
  JobList,
  JobStatus,
  Label,
  LabelGroup,
  LevelAnalysis,
  MeasureKey,
  Suggestion,
} from '../types'

export class ContractError extends Error {
  readonly path: string

  constructor(path: string, detail: string) {
    super(`${path}: ${detail}`)
    this.name = 'ContractError'
    this.path = path
  }
}

type Obj = Record<string, unknown>

const STATUSES: JobStatus[] = ['pending', 'running', 'done', 'failed']
const GROUPS: LabelGroup[] = ['vertebra', 'disc', 'cord', 'canal']
const GROUP_COLOR: Record<LabelGroup, string> = {
  vertebra: '#8E6BBF',
  disc: '#2BB5C0',
  cord: '#E8D44D',
  canal: '#4A90C2',
}

const isNil = (v: unknown) => v === null || v === undefined

function obj(v: unknown, p: string): Obj {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v as Obj
  throw new ContractError(p, 'cần object')
}

function arr(v: unknown, p: string): unknown[] {
  if (Array.isArray(v)) return v
  throw new ContractError(p, 'cần mảng')
}

function str(v: unknown, p: string): string {
  if (typeof v === 'string') return v
  throw new ContractError(p, 'cần chuỗi')
}

function num(v: unknown, p: string): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v)
  throw new ContractError(p, 'cần số')
}

function bool(v: unknown, p: string): boolean {
  if (typeof v === 'boolean') return v
  if (v === 'true' || v === 1) return true
  if (v === 'false' || v === 0) return false
  throw new ContractError(p, 'cần true/false')
}

function oneOf<T extends string>(v: unknown, list: readonly T[], p: string): T {
  if (typeof v === 'string' && (list as readonly string[]).includes(v)) return v as T
  throw new ContractError(p, `cần một trong ${list.join(', ')}`)
}

const opt = <T>(v: unknown, fallback: T, parse: (v: unknown) => T): T => (isNil(v) ? fallback : parse(v))

export function parseHealth(raw: unknown): Health {
  const o = obj(raw, 'health')
  const q = isNil(o.queue) ? {} : obj(o.queue, 'health.queue')
  return {
    status: opt(o.status, 'ok', (v) => str(v, 'health.status')),
    gpu_available: opt(o.gpu_available, false, (v) => bool(v, 'health.gpu_available')),
    queue: {
      pending: opt(q.pending, 0, (v) => num(v, 'health.queue.pending')),
      running: opt(q.running, 0, (v) => num(v, 'health.queue.running')),
    },
    api_version: opt(o.api_version, '', (v) => String(v)),
  }
}

function inferGroup(value: number): LabelGroup {
  if (value === 1) return 'cord'
  if (value === 2) return 'canal'
  if (value >= 60) return 'disc'
  return 'vertebra'
}

export function parseLabels(raw: unknown): Label[] {
  const list = Array.isArray(raw) ? raw : arr(obj(raw, 'labels').labels, 'labels.labels')
  return list.map((item, i) => {
    const p = `labels[${i}]`
    const o = obj(item, p)
    const value = num(o.value, `${p}.value`)
    const group = GROUPS.includes(o.group as LabelGroup) ? (o.group as LabelGroup) : inferGroup(value)
    const color = typeof o.color === 'string' && /^#[0-9a-f]{6}$/i.test(o.color) ? o.color : GROUP_COLOR[group]
    return { value, name: opt(o.name, `label_${value}`, (v) => String(v)), group, color }
  })
}

export function parseCreated(raw: unknown): CreatedJob {
  const o = obj(raw, 'job')
  const job_id = str(o.job_id, 'job.job_id')
  return {
    job_id,
    status: opt(o.status, 'pending' as JobStatus, (v) => oneOf(v, STATUSES, 'job.status')),
    created_at: opt(o.created_at, '', (v) => str(v, 'job.created_at')),
    links: { self: `/jobs/${job_id}` },
  }
}

export function parseJobList(raw: unknown): JobList {
  const o = obj(raw, 'jobs')
  const items = arr(o.items, 'jobs.items').map((item, i) => {
    const p = `jobs.items[${i}]`
    const j = obj(item, p)
    return {
      job_id: str(j.job_id, `${p}.job_id`),
      status: oneOf(j.status, STATUSES, `${p}.status`),
      filename: opt(j.filename, '', (v) => str(v, `${p}.filename`)),
      created_at: opt(j.created_at, '', (v) => str(v, `${p}.created_at`)),
    }
  })
  return {
    items,
    total: opt(o.total, items.length, (v) => num(v, 'jobs.total')),
    limit: opt(o.limit, 20, (v) => num(v, 'jobs.limit')),
    offset: opt(o.offset, 0, (v) => num(v, 'jobs.offset')),
  }
}

function parseSuggestion(raw: unknown, p: string): Suggestion {
  const o = obj(raw, p)
  const label = str(o.label, `${p}.label`)
  const measure = str(o.measure, `${p}.measure`) as MeasureKey
  return {
    label,
    label_vi: opt(o.label_vi, label, (v) => str(v, `${p}.label_vi`)),
    measure,
    measure_vi: opt(o.measure_vi, measure, (v) => str(v, `${p}.measure_vi`)),
    value: num(o.value, `${p}.value`),
    rule: oneOf(o.rule, ['>=', '<='] as const, `${p}.rule`),
    threshold: num(o.threshold, `${p}.threshold`),
    threshold_unit: opt(o.threshold_unit, 'gốc' as const, (v) => oneOf(v, ['gốc', 'z'] as const, `${p}.threshold_unit`)),
    percentile: num(o.percentile, `${p}.percentile`),
    confidence: oneOf(o.confidence, ['cao', 'vừa'] as const, `${p}.confidence`),
    sensitivity: num(o.sensitivity, `${p}.sensitivity`),
    specificity: num(o.specificity, `${p}.specificity`),
    ppv: num(o.ppv, `${p}.ppv`),
  }
}

function parseLevel(raw: unknown, p: string): LevelAnalysis {
  const o = obj(raw, p)
  const measures: LevelAnalysis['measures'] = {}
  if (!isNil(o.measures))
    for (const [k, v] of Object.entries(obj(o.measures, `${p}.measures`)))
      if (typeof v === 'number' && Number.isFinite(v)) measures[k as MeasureKey] = v
  return {
    level: str(o.level, `${p}.level`),
    missing: opt(o.missing, null, (v) => oneOf(v, ['disc', 'mid_slices'] as const, `${p}.missing`)),
    measures,
    suggestions: opt(o.suggestions, [] as unknown[], (v) => arr(v, `${p}.suggestions`)).map((s, i) =>
      parseSuggestion(s, `${p}.suggestions[${i}]`),
    ),
  }
}

export function parseAnalysis(raw: unknown, p = 'analysis'): Analysis | null {
  if (isNil(raw)) return null
  const o = obj(raw, p)
  const error = isNil(o.error)
    ? null
    : (() => {
        const e = obj(o.error, `${p}.error`)
        return { code: str(e.code, `${p}.error.code`), message: opt(e.message, '', (v) => str(v, `${p}.error.message`)) }
      })()
  const qc = isNil(o.qc)
    ? null
    : (() => {
        const q = obj(o.qc, `${p}.qc`)
        const warnings = opt(q.warnings, [] as unknown[], (v) => arr(v, `${p}.qc.warnings`)).map((w, i) => {
          const wo = obj(w, `${p}.qc.warnings[${i}]`)
          return {
            code: opt(wo.code, '', (v) => str(v, `${p}.qc.warnings[${i}].code`)),
            message: str(wo.message, `${p}.qc.warnings[${i}].message`),
          }
        })
        return { ok: bool(q.ok, `${p}.qc.ok`), warnings }
      })()
  return {
    qc,
    levels: opt(o.levels, [] as unknown[], (v) => arr(v, `${p}.levels`)).map((l, i) => parseLevel(l, `${p}.levels[${i}]`)),
    lordosis_deg: opt(o.lordosis_deg, null, (v) => num(v, `${p}.lordosis_deg`)),
    disclaimer: opt(o.disclaimer, null, (v) => str(v, `${p}.disclaimer`)),
    error,
  }
}

export function parseJob(raw: unknown): Job {
  const o = obj(raw, 'job')
  const status = oneOf(o.status, STATUSES, 'job.status')
  const input = isNil(o.input) ? {} : obj(o.input, 'job.input')
  const options = isNil(o.options) ? {} : obj(o.options, 'job.options')
  const nullableStr = (v: unknown, p: string) => opt(v, null, (x) => str(x, p))

  let result: Job['result'] = null
  if (status === 'done') {
    const r = obj(o.result, 'job.result')
    result = {
      input_url: str(r.input_url, 'job.result.input_url'),
      segmentation_url: str(r.segmentation_url, 'job.result.segmentation_url'),
      labels_url: opt(r.labels_url, '/labels', (v) => str(v, 'job.result.labels_url')),
      labels_present: opt(r.labels_present, [] as unknown[], (v) => arr(v, 'job.result.labels_present')).map((v, i) =>
        num(v, `job.result.labels_present[${i}]`),
      ),
      analysis: parseAnalysis(r.analysis, 'job.result.analysis'),
    }
  }

  let error: Job['error'] = null
  if (status === 'failed') {
    const e = isNil(o.error) ? {} : obj(o.error, 'job.error')
    error = {
      code: opt(e.code, 'UNKNOWN', (v) => str(v, 'job.error.code')),
      message: opt(e.message, 'Job thất bại.', (v) => str(v, 'job.error.message')),
      log_tail: opt(e.log_tail, undefined, (v) => str(v, 'job.error.log_tail')),
    }
  }

  return {
    job_id: str(o.job_id, 'job.job_id'),
    status,
    queue_position: opt(o.queue_position, null, (v) => num(v, 'job.queue_position')),
    input: {
      filename: opt(input.filename ?? o.filename, '', (v) => str(v, 'job.input.filename')),
      size_bytes: opt(input.size_bytes, 0, (v) => num(v, 'job.input.size_bytes')),
    },
    options: {
      iso: opt(options.iso, false, (v) => bool(v, 'job.options.iso')),
      step1_only: opt(options.step1_only, false, (v) => bool(v, 'job.options.step1_only')),
    },
    created_at: opt(o.created_at, '', (v) => str(v, 'job.created_at')),
    started_at: nullableStr(o.started_at, 'job.started_at'),
    finished_at: nullableStr(o.finished_at, 'job.finished_at'),
    duration_seconds: opt(o.duration_seconds, null, (v) => num(v, 'job.duration_seconds')),
    result,
    error,
  }
}
