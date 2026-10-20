import type { ReactNode } from 'react'

interface Props {
  code: string
  message: string
  children?: ReactNode
}

export default function ErrorBox({ code, message, children }: Props) {
  return (
    <div className="err" role="alert">
      <div className="code">{code}</div>
      {message}
      {children}
    </div>
  )
}
