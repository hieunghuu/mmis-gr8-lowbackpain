import { Suspense, lazy, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getLabels, resolveUrl } from '../api'
import AnalysisPanel from '../components/AnalysisPanel'
import ErrorBox from '../components/ErrorBox'
import { JOB_ERROR_HINT, formatUtc, mmss } from '../format'
import { useJob } from '../hooks/useJob'
import type { Job, Label } from '../types'

const Viewer = lazy(() => import('../components/Viewer'))

const STEPS = ['pending', 'running', 'done'] as const

export default function JobPage() {
  const { jobId = '' } = useParams()
  const { job, error } = useJob(jobId)

  if (error?.status === 404)
    return (
      <section>
        <h1>Job không còn tồn tại</h1>
        <p className="muted">Job này đã bị xóa hoặc chưa từng có.</p>
        <Link className="btn" to="/">
          Tải ảnh khác
        </Link>
      </section>
    )
  if (!job)
    return (
      <section>
        {error ? <ErrorBox code={error.code} message={error.message} /> : <p className="muted">Đang tải…</p>}
      </section>
    )

  return (
    <section>
      <div className="jobhead">
        <div>
          <h1>{job.input.filename}</h1>
          <div className="meta">
            job <b className="code">{job.job_id}</b>
            {job.input.dicom && (
              <>
                <br />
                DICOM: chọn series <b>{job.input.dicom.series_description}</b> (số {job.input.dicom.series_number},{' '}
                {job.input.dicom.n_slices} lát) trong {job.input.dicom.n_series} series
              </>
            )}
          </div>
        </div>
        <div className="meta">
          tạo lúc <b>{formatUtc(job.created_at)}</b> UTC
          <br />
          iso <b>{String(job.options.iso)}</b> · step1_only <b>{String(job.options.step1_only)}</b>
          {job.status === 'done' && job.duration_seconds !== null && (
            <>
              <br />
              xử lý <b>{job.duration_seconds}</b> giây
            </>
          )}
        </div>
      </div>
      {error && <ErrorBox code={error.code} message={error.message} />}
      <Steps status={job.status} />
      {job.status === 'pending' && <Pending job={job} />}
      {job.status === 'running' && <Running job={job} />}
      {job.status === 'failed' && <Failed job={job} />}
      {job.status === 'done' && job.result && <Done job={job} />}
    </section>
  )
}

function Steps({ status }: { status: Job['status'] }) {
  const idx = status === 'pending' ? 0 : status === 'running' ? 1 : 2
  return (
    <div className="steps">
      {STEPS.map((s, i) => (
        <div key={s} className={i === idx ? `on ${status === 'failed' ? 'failed' : ''}` : ''}>
          {i === 2 && status === 'failed' ? 'Failed' : s[0].toUpperCase() + s.slice(1)}
        </div>
      ))}
    </div>
  )
}

function Pending({ job }: { job: Job }) {
  return (
    <div className="panel">
      <div className="status-body">
        <div className="bignum">
          {job.queue_position ?? '–'}
          <small>vị trí trong hàng chờ</small>
        </div>
        <div>
          <b>Đang chờ tới lượt.</b>
        </div>
      </div>
    </div>
  )
}

function Running({ job }: { job: Job }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(t)
  }, [])
  const start = job.started_at ? new Date(job.started_at).getTime() : now
  return (
    <div className="panel">
      <div className="status-body">
        <div className="bignum">
          {mmss(Math.max(0, Math.floor((now - start) / 1000)))}
          <small>thời gian đã chạy</small>
        </div>
        <div>
          <b>Đang phân đoạn bằng TotalSpineSeg trên GPU.</b>
          <div className="bar" role="progressbar" aria-label="Đang chạy" />
        </div>
      </div>
    </div>
  )
}

function Failed({ job }: { job: Job }) {
  const e = job.error
  return (
    <div className="failbox">
      <div className="code">{e?.code ?? 'UNKNOWN'}</div>
      <p className="strong">{e?.message ?? 'Job thất bại.'}</p>
      {e && JOB_ERROR_HINT[e.code] && <p className="muted">{JOB_ERROR_HINT[e.code]}</p>}
      {e?.log_tail && <pre className="log">{e.log_tail}</pre>}
      <div className="actions">
        <Link className="btn" to="/">
          Tải ảnh khác
        </Link>
      </div>
    </div>
  )
}

function ViewerPlaceholder() {
  return (
    <div className="viewer">
      <div className="stage">
        <div className="overlay">Đang tải…</div>
      </div>
    </div>
  )
}

let labelsPromise: Promise<Label[]> | null = null
const loadLabels = () => (labelsPromise ??= getLabels().catch((e) => ((labelsPromise = null), Promise.reject(e))))

function Done({ job }: { job: Job }) {
  const result = job.result!
  const [labels, setLabels] = useState<Label[] | null>(null)
  const [labelsFailed, setLabelsFailed] = useState(false)
  const [level, setLevel] = useState('L3-L4')

  useEffect(() => {
    let alive = true
    loadLabels().then(
      (l) => alive && setLabels(l),
      () => alive && setLabelsFailed(true),
    )
    return () => {
      alive = false
    }
  }, [])

  const analysis = result.analysis
  const levels = analysis?.levels ?? []
  const defaultLevel = levels.find((l) => l.suggestions.length)?.level ?? levels[0]?.level ?? ''
  useEffect(() => setLevel(defaultLevel), [defaultLevel])

  return (
    <div className="work">
      {labels ? (
        <Suspense fallback={<ViewerPlaceholder />}>
          <Viewer
            inputUrl={resolveUrl(result.input_url)}
            segUrl={resolveUrl(result.segmentation_url)}
            labels={labels}
            labelsPresent={result.labels_present}
            level={level || null}
          />
        </Suspense>
      ) : labelsFailed ? (
        <ErrorBox code="LABELS_UNAVAILABLE" message="Không tải được bảng nhãn nên chưa hiển thị được mask." />
      ) : (
        <ViewerPlaceholder />
      )}
      <AnalysisPanel analysis={analysis} level={level} onSelect={setLevel} />
    </div>
  )
}
