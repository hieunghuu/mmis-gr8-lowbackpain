import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import JobListPage from './pages/JobListPage'
import JobPage from './pages/JobPage'
import UploadPage from './pages/UploadPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<UploadPage />} />
        <Route path="jobs" element={<JobListPage />} />
        <Route path="jobs/:jobId" element={<JobPage />} />
        <Route path="*" element={<UploadPage />} />
      </Route>
    </Routes>
  )
}
