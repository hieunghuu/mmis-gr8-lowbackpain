import { ANALYSIS_ERROR_HINT, MEASURES, fmt, measureUnit } from '../format'
import type { Analysis, LevelAnalysis, MeasureKey, Suggestion } from '../types'

interface Props {
  analysis: Analysis | null
  level: string
  onSelect: (level: string) => void
}

export default function AnalysisPanel({ analysis, level, onSelect }: Props) {
  if (!analysis) {
    return (
      <div className="panel">
        <b>Không có phân tích.</b>
        <div className="muted">Chỉ có khi iso và step1_only đều tắt.</div>
      </div>
    )
  }
  if (analysis.error) {
    return (
      <div className="failbox">
        <div className="code">{analysis.error.code}</div>
        <p className="strong">{analysis.error.message}</p>
        {ANALYSIS_ERROR_HINT[analysis.error.code] && <p className="muted">{ANALYSIS_ERROR_HINT[analysis.error.code]}</p>}
      </div>
    )
  }

  const qc = analysis.qc
  const qcOk = qc?.ok ?? true
  const selected = analysis.levels.find((l) => l.level === level)

  return (
    <div>
      <div className="sumrow">
        <span>
          Kiểm tra chất lượng <b style={{ color: qcOk ? 'var(--ok)' : 'var(--warn)' }}>{qcOk ? 'ĐẠT' : 'CẢNH BÁO'}</b>
        </span>
        {analysis.lordosis_deg !== null && (
          <span>
            Góc ưỡn thắt lưng <b>{fmt(analysis.lordosis_deg, 1)}°</b>
          </span>
        )}
        <span>
          Đo được <b>{analysis.levels.filter((l) => !l.missing).length}/{analysis.levels.length}</b> tầng
        </span>
      </div>

      {qc && !qc.ok && (
        <div className="notice warnlist">
          <b>Cảnh báo</b>
          <ul>
            {qc.warnings.map((w) => (
              <li key={w.code}>{w.message}</li>
            ))}
          </ul>
        </div>
      )}

      {analysis.disclaimer && (
        <div className="notice">
          <b>Lưu ý</b>
          <span>{analysis.disclaimer}</span>
        </div>
      )}

      <div className="scroll">
        <table className="levels">
          <thead>
            <tr>
              <th>Tầng</th>
              <th>Gợi ý</th>
              <th className="r">Số</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {analysis.levels.map((l) => (
              <LevelRow key={l.level} level={l} selected={l.level === level} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
      </div>

      {selected && <LevelDetail level={selected} qcOk={qcOk} />}
    </div>
  )
}

/** Mỗi bệnh một lần, lấy gợi ý có PPV cao nhất. */
function topSuggestions(l: LevelAnalysis): Suggestion[] {
  const seen = new Set<string>()
  return [...l.suggestions]
    .sort((a, b) => b.ppv - a.ppv)
    .filter((s) => (seen.has(s.label_vi) ? false : (seen.add(s.label_vi), true)))
}

function Confidence({ value }: { value: Suggestion['confidence'] }) {
  return <i className={`cf ${value === 'cao' ? 'cao' : ''}`}>{value === 'cao' ? 'Cao' : 'Vừa'}</i>
}

function LevelRow({ level, selected, onSelect }: { level: LevelAnalysis; selected: boolean; onSelect: (l: string) => void }) {
  const top = topSuggestions(level)
  return (
    <tr className={selected ? 'sel' : ''} onClick={() => onSelect(level.level)}>
      <td className="lv">{level.level}</td>
      <td>
        {level.missing ? (
          <span className="none">Không đo được</span>
        ) : top.length ? (
          <div className="chips">
            {top.slice(0, 2).map((s) => (
              <span className="chip" key={s.label}>
                {s.label_vi} <Confidence value={s.confidence} />
              </span>
            ))}
            {top.length > 2 && <span className="chip none">+{top.length - 2}</span>}
          </div>
        ) : (
          <span className="none">Không có gợi ý</span>
        )}
      </td>
      <td className="cnt">{level.suggestions.length}</td>
      <td className="r">
        <button className="btn small" type="button" aria-pressed={selected}>
          Chi tiết
        </button>
      </td>
    </tr>
  )
}

function LevelDetail({ level, qcOk }: { level: LevelAnalysis; qcOk: boolean }) {
  const flagged = new Set<MeasureKey>(level.suggestions.map((s) => s.measure))
  const groups = new Map<MeasureKey, Suggestion[]>()
  level.suggestions.forEach((s) => groups.set(s.measure, [...(groups.get(s.measure) ?? []), s]))

  return (
    <div className="detail">
      <div className="dhead">
        <strong>{level.level}</strong>
        <span>{level.suggestions.length ? `${level.suggestions.length} gợi ý theo ${groups.size} số đo` : ''}</span>
      </div>
      <dl className="measures">
        {MEASURES.map((m) => {
          const v = level.measures[m.key]
          return (
            <div key={m.key}>
              <dt>{m.name}</dt>
              <dd className={flagged.has(m.key) ? 'flag' : ''}>
                {v === undefined ? '—' : fmt(v, m.digits)} <small>{m.unit}</small>
              </dd>
            </div>
          )
        })}
      </dl>
      {level.missing ? (
        <div className="grp none">Không đo được tầng này (thiếu {level.missing === 'disc' ? 'đĩa đệm' : 'lát giữa'}).</div>
      ) : groups.size ? (
        [...groups.entries()].map(([measure, list]) => <MeasureGroup key={measure} measure={measure} list={list} />)
      ) : qcOk ? (
        <div className="grp none">Mọi số đo của tầng này nằm trong ngưỡng.</div>
      ) : null}
    </div>
  )
}

function MeasureGroup({ measure, list }: { measure: MeasureKey; list: Suggestion[] }) {
  const sorted = [...list].sort((a, b) => b.ppv - a.ppv)
  const first = sorted[0]
  const p = first.percentile
  const unit = measureUnit(measure)
  const name = first.measure_vi.charAt(0).toUpperCase() + first.measure_vi.slice(1)

  return (
    <div className="grp">
      <div className="ghead">
        <div className="t">
          {name}
          <br />
          <b>
            {fmt(first.value, 3)} {unit}
          </b>
        </div>
        <div className="pct">
          <div className="track">
            <span className="mark" style={{ left: `${p}%` }} />
          </div>
          <small>{p >= 50 ? `Cao hơn ${p}% bệnh nhân cùng tầng` : `Thấp hơn ${100 - p}% bệnh nhân cùng tầng`}</small>
        </div>
      </div>
      <ul className="sug">
        {sorted.map((s) => (
          <li key={s.label}>
            <span className="lab">{s.label_vi}</span>
            <span className={`conf ${s.confidence === 'cao' ? 'cao' : ''}`}>{s.confidence === 'cao' ? 'Cao' : 'Vừa'}</span>
            <span className="rule">
              {s.threshold_unit === 'z'
                ? `z-score ${s.rule === '>=' ? '≥' : '≤'} ${fmt(s.threshold, 3)}`
                : `${s.rule === '>=' ? '≥' : '≤'} ${fmt(s.threshold, 3)} ${unit}`}
            </span>
            <span className="stat">
              <span>
                Độ nhạy <b>{fmt(s.sensitivity, 2)}</b>
              </span>
              <span>
                Độ đặc hiệu <b>{fmt(s.specificity, 2)}</b>
              </span>
              <span className={s.ppv < 0.2 ? 'ppvlow' : ''}>
                PPV <b>{fmt(s.ppv, 2)}</b>
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
