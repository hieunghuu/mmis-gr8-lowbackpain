import { Niivue, SHOW_RENDER } from '@niivue/niivue'
import { useEffect, useMemo, useRef, useState } from 'react'
import { DISC_LABEL, GROUP_NAME, GROUP_ORDER } from '../format'
import type { Label, LabelGroup } from '../types'

interface Props {
  inputUrl: string
  segUrl: string
  labels: Label[]
  labelsPresent: number[]
  level: string | null
}

type View = 'multi' | 'sagittal' | 'axial' | 'coronal'
const VIEWS: { id: View; text: string }[] = [
  { id: 'multi', text: '3 mặt cắt' },
  { id: 'sagittal', text: 'Sagittal' },
  { id: 'axial', text: 'Axial' },
  { id: 'coronal', text: 'Coronal' },
]

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function buildLut(labels: Label[], hidden: Set<LabelGroup>) {
  const max = Math.max(...labels.map((l) => l.value))
  const lut = new Uint8ClampedArray((max + 1) * 4)
  const names: string[] = Array(max + 1).fill('')
  for (const l of labels) {
    const [r, g, b] = hexToRgb(l.color)
    lut.set([r, g, b, hidden.has(l.group) ? 0 : 255], l.value * 4)
    names[l.value] = l.name
  }
  return { lut, min: 0, max, labels: names }
}

function centroid(img: ArrayLike<number>, dims: number[], label: number): [number, number, number] | null {
  const [nx, ny, nz] = [dims[1], dims[2], dims[3]]
  let n = 0, sx = 0, sy = 0, sz = 0
  for (let z = 0; z < nz; z++)
    for (let y = 0; y < ny; y++) {
      const row = z * nx * ny + y * nx
      for (let x = 0; x < nx; x++)
        if (img[row + x] === label) {
          n++
          sx += x
          sy += y
          sz += z
        }
    }
  return n ? [sx / n, sy / n, sz / n] : null
}

export default function Viewer({ inputUrl, segUrl, labels, labelsPresent, level }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const nvRef = useRef<Niivue | null>(null)
  const [ready, setReady] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [view, setView] = useState<View>('multi')
  const [opacity, setOpacity] = useState(100)
  const [hidden, setHidden] = useState<Set<LabelGroup>>(new Set())

  const legend = useMemo(() => {
    const present = new Set(labelsPresent)
    return GROUP_ORDER.flatMap((g) => {
      const first = labels.find((l) => l.group === g && present.has(l.value))
      return first ? [{ group: g, color: first.color }] : []
    })
  }, [labels, labelsPresent])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let alive = true
    const nv = new Niivue({
      backColor: [0, 0, 0, 1],
      crosshairColor: [1, 0.2, 0.2, 0.8],
      show3Dcrosshair: false,
      isColorbar: false,
      multiplanarShowRender: SHOW_RENDER.NEVER,
      loadingText: 'Đang tải ảnh…',
    })
    nvRef.current = nv
    setReady(false)
    setLoadError(null)
    nv.attachToCanvas(canvas)
      .then(() =>
        nv.loadVolumes([
          { url: inputUrl, name: 'input.nii.gz' },
          { url: segUrl, name: 'segmentation.nii.gz', opacity: 1, colormapLabel: buildLut(labels, new Set()) },
        ]),
      )
      .then(() => {
        if (!alive) return
        nv.setSliceType(nv.sliceTypeMultiplanar)
        setReady(true)
      })
      .catch(() => alive && setLoadError('Không tải được ảnh. Kiểm tra kết nối rồi mở lại trang.'))
    return () => {
      alive = false
      nv.cleanup()
      nvRef.current = null
    }
  }, [inputUrl, segUrl, labels])

  useEffect(() => {
    const nv = nvRef.current
    if (!ready || !nv) return
    nv.setSliceType(
      { multi: nv.sliceTypeMultiplanar, sagittal: nv.sliceTypeSagittal, axial: nv.sliceTypeAxial, coronal: nv.sliceTypeCoronal }[view],
    )
  }, [view, ready])

  useEffect(() => {
    const nv = nvRef.current
    if (ready && nv) nv.setOpacity(1, opacity / 100)
  }, [opacity, ready])

  useEffect(() => {
    const nv = nvRef.current
    if (!ready || !nv) return
    nv.volumes[1].colormapLabel = buildLut(labels, hidden)
    nv.updateGLVolume()
  }, [hidden, ready, labels])

  useEffect(() => {
    const nv = nvRef.current
    if (!ready || !nv || !level) return
    const label = DISC_LABEL[level]
    const seg = nv.volumes[1]
    const dims = seg.dimsRAS
    if (!label || !dims) return
    const c = centroid(seg.img2RAS(), dims, label)
    if (!c) return
    nv.scene.crosshairPos = nv.vox2frac(c, 0)
    nv.updateGLVolume()
  }, [level, ready])

  const toggle = (g: LabelGroup) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })

  return (
    <div className="viewer">
      <div className="vbar">
        <div className="vtabs" role="group" aria-label="Mặt cắt">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" aria-pressed={view === v.id} onClick={() => setView(v.id)}>
              {v.text}
            </button>
          ))}
        </div>
        {level && (
          <span>
            Tầng <b className="vlevel">{level}</b>
          </span>
        )}
      </div>
      <div className="stage">
        <canvas ref={canvasRef} aria-label="Ảnh MRI cột sống kèm mask phân đoạn" />
        {!ready && !loadError && <div className="overlay">Đang tải ảnh…</div>}
        {loadError && <div className="overlay">{loadError}</div>}
      </div>
      <div className="vfoot">
        <div className="row">
          <label htmlFor="mask-opacity">Độ đậm mask</label>
          <input
            id="mask-opacity"
            type="range"
            min={0}
            max={100}
            value={opacity}
            onChange={(e) => setOpacity(Number(e.target.value))}
          />
          <output htmlFor="mask-opacity">{opacity}%</output>
        </div>
        <div className="legend">
          {legend.map(({ group, color }) => (
            <label key={group} className={hidden.has(group) ? 'off' : ''}>
              <input type="checkbox" checked={!hidden.has(group)} onChange={() => toggle(group)} />
              <span className="sw" style={{ background: color }} />
              {GROUP_NAME[group]}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
