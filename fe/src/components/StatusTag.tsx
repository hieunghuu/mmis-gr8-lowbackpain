import { STATUS_TEXT } from '../format'
import type { JobStatus } from '../types'

export default function StatusTag({ status }: { status: JobStatus }) {
  return <span className={`tag ${status}`}>{STATUS_TEXT[status]}</span>
}
