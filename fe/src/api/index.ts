import { ApiError, request } from './client'
import { ContractError, parseCreated, parseHealth, parseJob, parseJobList, parseLabels } from './validate'
import type { CreateJobInput, JobStatus } from '../types'

export { ApiError, resolveUrl } from './client'

async function checked<T>(raw: Promise<unknown>, parse: (v: unknown) => T): Promise<T> {
  const value = await raw
  try {
    return parse(value)
  } catch (e) {
    if (e instanceof ContractError)
      throw new ApiError(200, 'CONTRACT_MISMATCH', `Dữ liệu từ máy chủ không đúng spec (${e.message}).`)
    throw e
  }
}

export const getHealth = () => checked(request('/health'), parseHealth)

export const getJob = (jobId: string) => checked(request(`/jobs/${encodeURIComponent(jobId)}`), parseJob)

export function listJobs(params: { status?: JobStatus | ''; limit?: number; offset?: number }) {
  const q = new URLSearchParams()
  if (params.status) q.set('status', params.status)
  q.set('limit', String(params.limit ?? 20))
  q.set('offset', String(params.offset ?? 0))
  return checked(request(`/jobs?${q}`), parseJobList)
}

export function createJob({ file, iso, step1_only }: CreateJobInput) {
  const body = new FormData()
  body.append('file', file)
  body.append('iso', String(iso))
  body.append('step1_only', String(step1_only))
  return checked(request('/jobs', { method: 'POST', body }), parseCreated)
}

export const deleteJob = (jobId: string) =>
  request<void>(`/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })

export const getLabels = () => checked(request('/labels'), parseLabels)
