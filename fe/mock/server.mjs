// Mock BE theo docs/spec.md (mục 3, 4, 8) để FE chạy được khi chưa có GPU / BE thật.
// Không phụ thuộc thư viện nào: node mock/server.mjs  (cổng 8000, đổi bằng PORT).
// Ảnh nền và mask đều dùng ai/demo/0100_seg.nii.gz (giống MOCK_WORKER=1 của spec),
// analysis lấy từ ai/demo/analysis_0100.json.

import http from 'node:http'
import { readFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const demoDir = path.resolve(here, '../../ai/demo')
const MASK = readFileSync(path.join(demoDir, '0100_seg.nii.gz'))
const ANALYSIS = JSON.parse(readFileSync(path.join(demoDir, 'analysis_0100.json'), 'utf8'))

const PORT = Number(process.env.PORT ?? 8000)
const PREFIX = '/api/v1'
const MAX_UPLOAD = 200 * 1024 * 1024
const MAX_PENDING = 20
const PENDING_MS = 3000 // từ lúc tạo đến lúc chạy
const RUNNING_MS = 5000 // thời gian chạy giả lập

const ms = (iso) => new Date(iso).getTime()
const iso = (t) => new Date(t).toISOString().replace(/\.\d{3}Z$/, 'Z')

/* ---------- dữ liệu ---------- */

const LABELS_PRESENT = [1, 2, 32, 41, 42, 43, 44, 45, 50, 91, 92, 93, 94, 95, 100]

function buildLabels() {
  const out = [
    { value: 1, name: 'spinal_cord', group: 'cord', color: '#E8D44D' },
    { value: 2, name: 'spinal_canal', group: 'canal', color: '#4A90C2' },
  ]
  const vert = (from, count, prefix, start) => {
    for (let i = 0; i < count; i++) out.push({ value: from + i, name: `vertebrae_${prefix}${start + i}`, group: 'vertebra', color: '#8E6BBF' })
  }
  vert(11, 7, 'C', 1)
  vert(21, 12, 'T', 1)
  vert(41, 5, 'L', 1)
  out.push({ value: 50, name: 'sacrum', group: 'vertebra', color: '#B9A6D6' })
  const disc = (value, name) => out.push({ value, name, group: 'disc', color: '#2BB5C0' })
  for (let i = 0; i < 5; i++) disc(63 + i, `disc_C${2 + i}_C${3 + i}`)
  disc(71, 'disc_C7_T1')
  for (let i = 0; i < 11; i++) disc(72 + i, `disc_T${1 + i}_T${2 + i}`)
  disc(91, 'disc_T12_L1'); disc(92, 'disc_L1_L2'); disc(93, 'disc_L2_L3'); disc(94, 'disc_L3_L4'); disc(95, 'disc_L4_L5')
  disc(100, 'disc_L5_S')
  return out
}
const LABELS = buildLabels()

const jobs = new Map()
const now = Date.now()
function seed(filename, status, minutesAgo, extra = {}) {
  const created = now - minutesAgo * 60000
  const id = randomUUID()
  const job = { id, filename, size: 18350212, iso: false, step1: false, created: iso(created), ...extra }
  job.forced = status // trạng thái cố định cho job mẫu
  jobs.set(id, job)
}
seed('sub-0100_T2w.nii.gz', 'done', 60, { duration: 155 })
seed('sub-0113_T2w.nii.gz', 'done', 95, { duration: 161 })
seed('sub-0102_T2w.nii.gz', 'failed', 130, { duration: 48 })

/* ---------- trạng thái job ---------- */

function stateOf(job) {
  if (job.forced) return job.forced
  const age = Date.now() - ms(job.created)
  if (age < PENDING_MS) return 'pending'
  if (age < PENDING_MS + RUNNING_MS) return 'running'
  return 'done'
}

function queuePosition(job) {
  let pos = 1
  for (const j of jobs.values()) if (stateOf(j) === 'pending' && ms(j.created) < ms(job.created)) pos++
  return pos
}

function view(job) {
  const status = stateOf(job)
  const id = job.id
  const startedAt = status === 'pending' ? null : iso(ms(job.created) + (job.forced ? 5000 : PENDING_MS))
  const dur = job.duration ?? (status === 'done' ? Math.round(RUNNING_MS / 1000) : null)
  const finishedAt = status === 'done' || status === 'failed' ? iso(ms(startedAt) + (dur ?? 0) * 1000) : null
  const base = {
    job_id: id,
    status,
    queue_position: status === 'pending' ? queuePosition(job) : null,
    input: { filename: job.filename, size_bytes: job.size },
    options: { iso: job.iso, step1_only: job.step1 },
    created_at: job.created,
    started_at: startedAt,
    finished_at: finishedAt,
    duration_seconds: status === 'done' || status === 'failed' ? dur : null,
    result: null,
    error: null,
  }
  if (status === 'done') {
    base.result = {
      input_url: `${PREFIX}/jobs/${id}/input`,
      segmentation_url: `${PREFIX}/jobs/${id}/result`,
      labels_url: `${PREFIX}/labels`,
      labels_present: LABELS_PRESENT,
      analysis: job.iso || job.step1 ? null : ANALYSIS,
    }
  }
  if (status === 'failed') {
    base.error = {
      code: 'SEGMENTATION_FAILED',
      message: 'TotalSpineSeg thoát với mã 1',
      log_tail: 'RuntimeError: CUDA out of memory. Tried to allocate 1.20 GiB\nExit code 1',
    }
  }
  return base
}

/* ---------- HTTP ---------- */

const cors = {
  'Access-Control-Allow-Origin': process.env.CORS_ORIGINS ?? 'http://localhost:5173',
  'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Expose-Headers': 'Content-Disposition',
}

function send(res, status, body, headers = {}) {
  const isBuf = Buffer.isBuffer(body)
  const payload = body === undefined ? '' : isBuf ? body : JSON.stringify(body)
  res.writeHead(status, {
    ...cors,
    ...(body !== undefined && !isBuf ? { 'Content-Type': 'application/json; charset=utf-8' } : {}),
    ...headers,
  })
  res.end(payload)
}

const fail = (res, status, code, message, details) =>
  send(res, status, { error: { code, message, ...(details ? { details } : {}) } })

function readBody(req) {
  return new Promise((resolve) => {
    const chunks = []
    req.on('data', (c) => chunks.push(c))
    req.on('end', () => resolve(Buffer.concat(chunks)))
  })
}

async function createJob(req, res) {
  const declared = Number(req.headers['content-length'] ?? 0)
  if (declared > MAX_UPLOAD) return fail(res, 413, 'FILE_TOO_LARGE', 'File vượt quá 200 MB', { max_mb: 200 })
  const raw = await readBody(req)
  const text = raw.toString('latin1')
  const name = /filename="([^"]*)"/.exec(text)?.[1] ?? ''
  if (!/\.(nii|nii\.gz)$/i.test(name))
    return fail(res, 400, 'INVALID_FILE_TYPE', 'Chỉ chấp nhận file .nii hoặc .nii.gz', { filename: name })
  const opt = (key) => {
    const v = new RegExp(`name="${key}"\\r\\n\\r\\n([^\\r]*)`).exec(text)?.[1]
    if (v === undefined) return false
    if (v !== 'true' && v !== 'false') return null
    return v === 'true'
  }
  const iso_ = opt('iso'), step1 = opt('step1_only')
  if (iso_ === null || step1 === null)
    return fail(res, 400, 'INVALID_OPTION', 'iso và step1_only chỉ nhận true hoặc false')
  const pending = [...jobs.values()].filter((j) => stateOf(j) === 'pending').length
  if (pending >= MAX_PENDING) return fail(res, 503, 'QUEUE_FULL', 'Hàng chờ đã đầy, thử lại sau')

  const id = randomUUID()
  const job = { id, filename: name, size: raw.length, iso: iso_, step1, created: iso(Date.now()) }
  jobs.set(id, job)
  send(res, 202, {
    job_id: id,
    status: 'pending',
    created_at: job.created,
    links: { self: `${PREFIX}/jobs/${id}` },
  })
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  const p = url.pathname
  if (req.method === 'OPTIONS') return send(res, 204, undefined)
  if (!p.startsWith(PREFIX)) return fail(res, 404, 'JOB_NOT_FOUND', 'Không có đường dẫn này')
  const route = p.slice(PREFIX.length)

  if (req.method === 'GET' && route === '/health') {
    const all = [...jobs.values()].map(stateOf)
    return send(res, 200, {
      status: 'ok',
      gpu_available: true,
      queue: { pending: all.filter((s) => s === 'pending').length, running: all.filter((s) => s === 'running').length },
      api_version: '1.0.0-mock',
    })
  }
  if (req.method === 'GET' && route === '/labels') return send(res, 200, { labels: LABELS })

  if (route === '/jobs') {
    if (req.method === 'POST') return createJob(req, res)
    if (req.method === 'GET') {
      const status = url.searchParams.get('status')
      const limit = Math.min(Number(url.searchParams.get('limit') ?? 20) || 20, 100)
      const offset = Number(url.searchParams.get('offset') ?? 0) || 0
      const all = [...jobs.values()]
        .map((j) => ({ job_id: j.id, status: stateOf(j), filename: j.filename, created_at: j.created }))
        .filter((j) => !status || j.status === status)
        .sort((a, b) => ms(b.created_at) - ms(a.created_at))
      return send(res, 200, { items: all.slice(offset, offset + limit), total: all.length, limit, offset })
    }
  }

  const m = /^\/jobs\/([^/]+)(\/input|\/result)?$/.exec(route)
  if (m) {
    const job = jobs.get(m[1])
    if (!job) return fail(res, 404, 'JOB_NOT_FOUND', 'Không có job này', { job_id: m[1] })
    const status = stateOf(job)
    if (req.method === 'GET' && !m[2]) return send(res, 200, view(job))
    if (req.method === 'GET' && m[2]) {
      if (m[2] === '/result' && status !== 'done') return fail(res, 409, 'JOB_NOT_READY', 'Job chưa xong')
      const file = m[2] === '/input' ? `${job.id}_input.nii.gz` : `${job.id}_seg.nii.gz`
      return send(res, 200, MASK, {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="${file}"`,
      })
    }
    if (req.method === 'DELETE' && !m[2]) {
      if (status === 'running') return fail(res, 409, 'JOB_RUNNING', 'Job đang chạy, không xóa được')
      jobs.delete(job.id)
      return send(res, 204, undefined)
    }
  }
  fail(res, 404, 'JOB_NOT_FOUND', 'Không có đường dẫn này')
})

server.listen(PORT, () => console.log(`Mock BE: http://localhost:${PORT}${PREFIX}  (job mẫu: ${jobs.size})`))
