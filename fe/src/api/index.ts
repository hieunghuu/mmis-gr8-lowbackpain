import { request } from './client'
import type { CreateJobInput, CreatedJob, Health, Job, JobList, JobStatus, Label } from '../types'

export { ApiError, resolveUrl } from './client'

export const getHealth = () => request<Health>('/health')

export const getJob = (jobId: string) => request<Job>(`/jobs/${encodeURIComponent(jobId)}`)

export function listJobs(params: { status?: JobStatus | ''; limit?: number; offset?: number }) {
  const q = new URLSearchParams()
  if (params.status) q.set('status', params.status)
  q.set('limit', String(params.limit ?? 20))
  q.set('offset', String(params.offset ?? 0))
  return request<JobList>(`/jobs?${q}`)
}

export function createJob({ file, iso, step1_only }: CreateJobInput) {
  const body = new FormData()
  body.append('file', file)
  body.append('iso', String(iso))
  body.append('step1_only', String(step1_only))
  return request<CreatedJob>('/jobs', { method: 'POST', body })
}

export const deleteJob = (jobId: string) =>
  request<void>(`/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })

export const getLabels = () => request<{ labels: Label[] }>('/labels').then((r) => r.labels)
