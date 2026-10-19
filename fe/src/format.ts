import type { JobStatus, LabelGroup, MeasureKey } from './types'

export const fmt = (n: number, maxDigits = 2) =>
  n.toLocaleString('vi-VN', { maximumFractionDigits: maxDigits, minimumFractionDigits: 0 })

/** "2026-10-19T12:30:00Z" -> "2026-10-19 12:30:00" (UTC) */
export const formatUtc = (iso: string) => iso.replace('T', ' ').replace('Z', '')

export const formatSize = (bytes: number) => `${fmt(bytes / 1048576, 1)} MB`

export const mmss = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

export const MEASURES: { key: MeasureKey; name: string; unit: string; digits: number }[] = [
  { key: 'disc_height_mm', name: 'Chiều cao đĩa', unit: 'mm', digits: 1 },
  { key: 'dhi', name: 'Chỉ số chiều cao đĩa (DHI)', unit: '', digits: 3 },
  { key: 'disc_csf_ratio', name: 'Tín hiệu đĩa / dịch não tủy', unit: '', digits: 3 },
  { key: 'disc_vb_ratio', name: 'Tín hiệu đĩa / thân đốt', unit: '', digits: 3 },
  { key: 'disc_post_bulge_mm', name: 'Độ nhô ra sau của đĩa', unit: 'mm', digits: 2 },
  { key: 'canal_ap_mm', name: 'Ống sống trước–sau', unit: 'mm', digits: 2 },
  { key: 'canal_csa_approx_mm2', name: 'Diện tích ống sống', unit: 'mm²', digits: 0 },
  { key: 'listhesis_mm', name: 'Trượt đốt sống', unit: 'mm', digits: 2 },
]

export const measureUnit = (key: MeasureKey) => MEASURES.find((m) => m.key === key)?.unit ?? ''

export const GROUP_NAME: Record<LabelGroup, string> = {
  vertebra: 'Đốt sống',
  disc: 'Đĩa đệm',
  cord: 'Tủy sống',
  canal: 'Ống sống',
}
export const GROUP_ORDER: LabelGroup[] = ['vertebra', 'disc', 'cord', 'canal']

/** Nhãn voxel của đĩa đệm từng tầng (spec mục 7: 91–95 và 100). */
export const DISC_LABEL: Record<string, number> = {
  'T12-L1': 91,
  'L1-L2': 92,
  'L2-L3': 93,
  'L3-L4': 94,
  'L4-L5': 95,
  'L5-S1': 100,
}

export const STATUS_TEXT: Record<JobStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
}

/** Gợi ý hiển thị cho lỗi job và lỗi phân tích (spec mục 8). */
export const JOB_ERROR_HINT: Record<string, string> = {
  SEGMENTATION_FAILED: 'Thử lại. Nếu lặp lại thì gửi đoạn log cho người phụ trách.',
  OUTPUT_NOT_FOUND: 'Lỗi hệ thống, hãy báo cho người phụ trách.',
  TIMEOUT: 'Kiểm tra GPU hoặc kích thước ảnh.',
  WORKER_INTERRUPTED: 'Máy chủ vừa khởi động lại, hãy tạo lại job.',
  MULTIPLE_SERIES: 'Chỉ tải lên một series.',
}

export const ANALYSIS_ERROR_HINT: Record<string, string> = {
  GEOMETRY_MISMATCH: 'Chạy lại với iso tắt.',
  NOT_SAGITTAL: 'Chỉ phân tích ảnh sagittal T2 thắt lưng.',
  ANALYSIS_FAILED: 'Lỗi hệ thống. Mask vẫn xem được.',
}
