import { useEffect, useState } from 'react'
import { ApiError, getJob } from '../api'
import type { Job } from '../types'

const FAST_MS = 3000
const SLOW_MS = 10000
const SLOW_AFTER_MS = 120000

interface State {
  job: Job | null
  error: ApiError | null
}

export function useJob(jobId: string): State {
  const [state, setState] = useState<State>({ job: null, error: null })

  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const startedAt = Date.now()
    setState({ job: null, error: null })

    const tick = async () => {
      try {
        const job = await getJob(jobId)
        if (!alive) return
        setState({ job, error: null })
        if (job.status === 'done' || job.status === 'failed') return
      } catch (e) {
        if (!alive) return
        const err = e instanceof ApiError ? e : new ApiError(0, 'NETWORK_ERROR', 'Không kết nối được tới máy chủ.')
        setState((s) => ({ ...s, error: err }))
        if (err.status === 404) return
      }
      const wait = Date.now() - startedAt > SLOW_AFTER_MS ? SLOW_MS : FAST_MS
      timer = window.setTimeout(tick, wait)
    }
    tick()

    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [jobId])

  return state
}
