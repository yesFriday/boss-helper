import { Component, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  handleReset = () => {
    this.setState({ error: null })
    window.location.reload()
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex items-center justify-center h-screen bg-slate-50">
          <div className="text-center p-8 max-w-md">
            <AlertTriangle size={48} className="mx-auto mb-4 text-red-400" />
            <h1 className="text-lg font-bold text-slate-800 mb-2">页面出现错误</h1>
            <p className="text-sm text-slate-500 mb-4 break-all">
              {this.state.error.message || '未知错误'}
            </p>
            <button
              onClick={this.handleReset}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-500 hover:bg-indigo-600 transition-colors cursor-pointer"
            >
              <RefreshCw size={14} />
              刷新页面
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
