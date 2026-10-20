import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, createJob } from '../api'
import ErrorBox from '../components/ErrorBox'
import { formatSize } from '../format'

const MAX_MB = 200

function validate(file: File): { code: string; message: string } | null {
  if (!/\.(nii|nii\.gz)$/i.test(file.name))
    return { code: 'INVALID_FILE_TYPE', message: `Chỉ chấp nhận file .nii hoặc .nii.gz. File ${file.name} không hợp lệ.` }
  if (file.size > MAX_MB * 1024 * 1024) return { code: 'FILE_TOO_LARGE', message: `File vượt quá ${MAX_MB} MB.` }
  return null
}

export default function UploadPage() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [iso, setIso] = useState(false)
  const [step1, setStep1] = useState(false)
  const [over, setOver] = useState(false)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [sending, setSending] = useState(false)

  const pick = (f: File | undefined) => {
    setFile(null)
    setError(null)
    if (!f) return
    const bad = validate(f)
    if (bad) setError(bad)
    else setFile(f)
  }

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setOver(false)
    pick(e.dataTransfer.files[0])
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) return
    setSending(true)
    setError(null)
    try {
      const job = await createJob({ file, iso, step1_only: step1 })
      navigate(`/jobs/${job.job_id}`)
    } catch (err) {
      const a = err instanceof ApiError ? err : null
      setError({ code: a?.code ?? 'INTERNAL_ERROR', message: a?.message ?? 'Đã có lỗi, thử lại sau.' })
      setSending(false)
    }
  }

  return (
    <section>
      <h1>Tải ảnh MRI lên</h1>
      <form className="grid-upload" onSubmit={onSubmit}>
        <label
          className={`drop ${over ? 'over' : ''}`}
          htmlFor="file"
          onDragOver={(e) => {
            e.preventDefault()
            setOver(true)
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <span className="big">Chọn file hoặc kéo thả vào đây</span>
          <span className="sub">.nii hoặc .nii.gz · tối đa {MAX_MB} MB · mỗi job một file</span>
          <input id="file" ref={inputRef} type="file" accept=".nii,.gz,.nii.gz" onChange={(e) => pick(e.target.files?.[0])} />
        </label>

        {file && (
          <div className="picked">
            <span className="fn">{file.name}</span>
            <span className="size">{formatSize(file.size)}</span>
          </div>
        )}
        {error && <ErrorBox code={error.code} message={error.message} />}

        <div className="opts">
          <label className="opt">
            <input type="checkbox" checked={iso} onChange={(e) => setIso(e.target.checked)} />
            <div>
              <b>Mask 1 mm đẳng hướng</b>
            </div>
          </label>
          <label className="opt">
            <input type="checkbox" checked={step1} onChange={(e) => setStep1(e.target.checked)} />
            <div>
              <b>Chỉ chạy bước 1</b>
            </div>
          </label>
        </div>

        <div>
          <button className="btn primary" type="submit" disabled={!file || sending}>
            {sending ? 'Đang gửi…' : 'Gửi phân đoạn'}
          </button>
        </div>
      </form>
    </section>
  )
}
