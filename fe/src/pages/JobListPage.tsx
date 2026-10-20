import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, deleteJob, listJobs } from '../api'
import ErrorBox from '../components/ErrorBox'
import StatusTag from '../components/StatusTag'
import { formatUtc } from '../format'
import type { JobList, JobStatus } from '../types'

const LIMIT = 20
const FILTERS: { value: JobStatus | ''; text: string }[] = [
  { value: '', text: 'Tất cả' },
  { value: 'pending', text: 'Pending' },
  { value: 'running', text: 'Running' },
  { value: 'done', text: 'Done' },
  { value: 'failed', text: 'Failed' },
]

export default function JobListPage() {
  const [status, setStatus] = useState<JobStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<JobList | null>(null)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await listJobs({ status, limit: LIMIT, offset }))
      setError(null)
    } catch (e) {
      const a = e instanceof ApiError ? e : null
      setError({ code: a?.code ?? 'INTERNAL_ERROR', message: a?.message ?? 'Không tải được danh sách.' })
    }
  }, [status, offset])

  useEffect(() => {
    load()
  }, [load])

  const remove = async (id: string) => {
    try {
      await deleteJob(id)
      setConfirming(null)
      await load()
    } catch (e) {
      const a = e instanceof ApiError ? e : null
      setConfirming(null)
      setError({ code: a?.code ?? 'INTERNAL_ERROR', message: a?.message ?? 'Không xóa được job.' })
    }
  }

  const pick = (s: JobStatus | '') => {
    setStatus(s)
    setOffset(0)
  }

  return (
    <section>
      <h1>Danh sách job</h1>
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Lọc theo trạng thái">
          {FILTERS.map((f) => (
            <button key={f.value} type="button" aria-pressed={status === f.value} onClick={() => pick(f.value)}>
              {f.text}
            </button>
          ))}
        </div>
        {data && <span className="total">total {data.total}</span>}
      </div>

      {error && <ErrorBox code={error.code} message={error.message} />}

      {data && data.items.length === 0 && <div className="empty">Không có job nào ở trạng thái này.</div>}
      {data && data.items.length > 0 && (
        <table className="jobs">
          <thead>
            <tr>
              <th>Job</th>
              <th>File</th>
              <th>Trạng thái</th>
              <th>Tạo lúc (UTC)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.items.map((j) => (
              <tr key={j.job_id}>
                <td data-l="Job">
                  <Link className="jl" to={`/jobs/${j.job_id}`}>
                    {j.job_id.slice(0, 8)}…
                  </Link>
                </td>
                <td data-l="File" className="code">
                  {j.filename}
                </td>
                <td data-l="Trạng thái">
                  <StatusTag status={j.status} />
                </td>
                <td data-l="Tạo lúc">{formatUtc(j.created_at)}</td>
                <td className="r">
                  {confirming === j.job_id ? (
                    <>
                      <button className="btn small danger" type="button" onClick={() => remove(j.job_id)}>
                        Xác nhận xóa
                      </button>{' '}
                      <button className="btn small" type="button" onClick={() => setConfirming(null)}>
                        Hủy
                      </button>
                    </>
                  ) : (
                    <button
                      className="btn small"
                      type="button"
                      disabled={j.status === 'running'}
                      title={j.status === 'running' ? 'Job đang chạy, không xóa được' : undefined}
                      onClick={() => setConfirming(j.job_id)}
                    >
                      Xóa
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data && data.total > LIMIT && (
        <div className="pager">
          <span>
            {offset + 1}–{Math.min(offset + LIMIT, data.total)} / {data.total}
          </span>
          <div className="btns">
            <button className="btn small" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
              Trước
            </button>
            <button
              className="btn small"
              type="button"
              disabled={offset + LIMIT >= data.total}
              onClick={() => setOffset(offset + LIMIT)}
            >
              Sau
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
