import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import JobListPage from './pages/JobListPage'
import JobPage from './pages/JobPage'
import UploadPage from './pages/UploadPage'

const GuidePage = lazy(() => import('./pages/GuidePage'))

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<UploadPage />} />
        <Route path="jobs" element={<JobListPage />} />
        <Route path="jobs/:jobId" element={<JobPage />} />
        <Route
          path="huong-dan"
          element={
            <Suspense fallback={<p className="muted">Đang tải…</p>}>
              <GuidePage />
            </Suspense>
          }
        />
        <Route path="*" element={<UploadPage />} />
      </Route>
    </Routes>
  )
}
