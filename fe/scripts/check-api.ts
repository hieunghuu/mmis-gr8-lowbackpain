import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { parseCreated, parseHealth, parseJob, parseJobList, parseLabels } from '../src/api/validate.ts'

const base = (process.argv[2] ?? process.env.API_URL ?? 'http://localhost:8000/api/v1').replace(/\/$/, '')
const timeoutSec = Number(process.env.CHECK_TIMEOUT ?? 1200)
const here = path.dirname(fileURLToPath(import.meta.url))
const sample = process.env.SAMPLE ?? path.resolve(here, '../../ai/demo/0100_seg.nii.gz')

let failed = 0
const ok = (name: string) => console.log(`  ✓ ${name}`)
const bad = (name: string, why: string) => {
  failed++
  console.log(`  ✗ ${name}\n      ${why}`)
}

async function call(p: string, init?: RequestInit) {
  const res = await fetch(base + p, init)
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  return { res, body }
}

async function step(name: string, fn: () => Promise<void>) {
  try {
    await fn()
    ok(name)
  } catch (e) {
    bad(name, e instanceof Error ? e.message : String(e))
  }
}

function expectStatus(actual: number, expected: number) {
  if (actual !== expected) throw new Error(`HTTP ${actual}, cần ${expected}`)
}

function expectError(body: unknown, code: string) {
  const e = (body as { error?: { code?: unknown; message?: unknown } } | null)?.error
  if (!e || e.code !== code || typeof e.message !== 'string')
    throw new Error(`body cần {"error": {"code": "${code}", "message": "..."}}, nhận ${JSON.stringify(body)}`)
}

const upload = (name: string, data: Uint8Array, extra: Record<string, string> = {}) => {
  const form = new FormData()
  form.append('file', new Blob([new Uint8Array(data)]), name)
  for (const [k, v] of Object.entries(extra)) form.append(k, v)
  return call('/jobs', { method: 'POST', body: form })
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

console.log(`Kiểm tra API theo docs/spec.md tại ${base}\n`)

try {
  await fetch(base + '/health')
} catch {
  console.log(`Không kết nối được ${base}. BE đã chạy chưa?`)
  process.exit(1)
}

await step('GET /health', async () => {
  const { res, body } = await call('/health')
  expectStatus(res.status, 200)
  parseHealth(body)
})

await step('GET /labels', async () => {
  const { res, body } = await call('/labels')
  expectStatus(res.status, 200)
  if (parseLabels(body).length === 0) throw new Error('danh sách nhãn rỗng')
})

await step('GET /jobs', async () => {
  const { res, body } = await call('/jobs?limit=5&offset=0')
  expectStatus(res.status, 200)
  parseJobList(body)
})

await step('GET /jobs/{id} không tồn tại → 404 JOB_NOT_FOUND', async () => {
  const { res, body } = await call('/jobs/00000000-0000-4000-8000-000000000000')
  expectStatus(res.status, 404)
  expectError(body, 'JOB_NOT_FOUND')
})

await step('POST /jobs sai đuôi file → 400 INVALID_FILE_TYPE', async () => {
  const { res, body } = await upload('scan.dcm', new Uint8Array([1, 2, 3]))
  expectStatus(res.status, 400)
  expectError(body, 'INVALID_FILE_TYPE')
})

await step('POST /jobs tùy chọn sai → 400 INVALID_OPTION', async () => {
  const { res, body } = await upload('scan.nii.gz', readFileSync(sample), { iso: 'maybe' })
  expectStatus(res.status, 400)
  expectError(body, 'INVALID_OPTION')
})

let jobId = ''
await step('POST /jobs ảnh mẫu → 202', async () => {
  const { res, body } = await upload('sample_T2w.nii.gz', readFileSync(sample), { iso: 'false', step1_only: 'false' })
  expectStatus(res.status, 202)
  jobId = parseCreated(body).job_id
})

if (jobId) {
  let status = ''
  await step(`GET /jobs/{id} đến khi xong (tối đa ${timeoutSec} giây)`, async () => {
    const until = Date.now() + timeoutSec * 1000
    while (Date.now() < until) {
      const { res, body } = await call(`/jobs/${jobId}`)
      expectStatus(res.status, 200)
      const job = parseJob(body)
      status = job.status
      if (status === 'done' || status === 'failed') {
        if (status === 'failed') console.log(`      job failed (${job.error?.code}: ${job.error?.message}), payload vẫn đúng spec`)
        return
      }
      await sleep(3000)
    }
    throw new Error(`quá ${timeoutSec} giây, trạng thái cuối: ${status}`)
  })

  if (status === 'done') {
    for (const [name, p] of [['input', `/jobs/${jobId}/input`], ['result', `/jobs/${jobId}/result`]]) {
      await step(`GET /jobs/{id}/${name} trả file .nii.gz`, async () => {
        const res = await fetch(base + p)
        expectStatus(res.status, 200)
        const buf = new Uint8Array(await res.arrayBuffer())
        if (buf.length < 100) throw new Error(`file quá nhỏ (${buf.length} byte)`)
        if (!(buf[0] === 0x1f && buf[1] === 0x8b)) throw new Error('không phải file gzip (.nii.gz)')
      })
    }
  }

  await step('DELETE /jobs/{id} → 204', async () => {
    const { res } = await call(`/jobs/${jobId}`, { method: 'DELETE' })
    expectStatus(res.status, 204)
  })
}

console.log(failed ? `\n${failed} mục chưa đúng spec.` : '\nTất cả đúng spec.')
process.exit(failed ? 1 : 0)
