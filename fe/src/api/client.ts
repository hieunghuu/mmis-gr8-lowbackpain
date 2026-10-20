const RAW_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'

export const API_BASE = RAW_BASE.replace(/\/$/, '')

const API_ORIGIN = /^https?:\/\//.test(API_BASE) ? new URL(API_BASE).origin : ''

export function resolveUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : API_ORIGIN + path
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details?: Record<string, unknown>

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null)
  const e = body?.error
  if (e && typeof e.code === 'string') return new ApiError(res.status, e.code, e.message ?? e.code, e.details)
  return new ApiError(res.status, 'INTERNAL_ERROR', `Máy chủ trả về lỗi ${res.status}.`)
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, init)
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'Không kết nối được tới máy chủ.')
  }
  if (!res.ok) throw await toApiError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
