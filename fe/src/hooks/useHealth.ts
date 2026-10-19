import { useEffect, useState } from 'react'
import { getHealth } from '../api'
import type { Health } from '../types'

export function useHealth(): Health | 'down' | null {
  const [health, setHealth] = useState<Health | 'down' | null>(null)
  useEffect(() => {
    let alive = true
    const load = () =>
      getHealth().then(
        (h) => alive && setHealth(h),
        () => alive && setHealth('down'),
      )
    load()
    const t = window.setInterval(load, 10000)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [])
  return health
}
