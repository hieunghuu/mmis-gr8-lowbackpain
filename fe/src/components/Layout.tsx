import { NavLink, Outlet } from 'react-router-dom'
import { useHealth } from '../hooks/useHealth'

export default function Layout() {
  const health = useHealth()
  return (
    <>
      <header className="sys">
        <div className="wrap">
          <div className="brand">
            <i />
            Spine MRI · MMIS Nhóm 8
          </div>
          <div className="grow" />
          <div className="health" aria-label="Trạng thái hệ thống">
            {health === 'down' ? (
              <span>
                <span className="dot bad" />
                api <b>không kết nối</b>
              </span>
            ) : health ? (
              <>
                <span>
                  <span className="dot" />
                  api <b>ok</b>
                </span>
                <span>
                  GPU <b>{health.gpu_available ? 'có' : 'không'}</b>
                </span>
                <span>
                  hàng chờ <b>{health.queue.pending}</b> chờ · <b>{health.queue.running}</b> chạy
                </span>
                <span>
                  v<b>{health.api_version}</b>
                </span>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <nav>
        <div className="wrap">
          <NavLink to="/" end>
            Tải ảnh lên
          </NavLink>
          <NavLink to="/jobs" end>
            Danh sách job
          </NavLink>
        </div>
      </nav>
      <main>
        <div className="wrap">
          <Outlet />
        </div>
      </main>
    </>
  )
}
