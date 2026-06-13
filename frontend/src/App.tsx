import { Sidebar } from './components/layout/Sidebar'
import { PageHeader } from './components/layout/PageHeader'
import { ToastContainer } from './components/common/ToastContainer'
import { SearchPage } from './pages/SearchPage'
import { ApplicationsPage } from './pages/ApplicationsPage'
import { ChatPage } from './pages/ChatPage'
import { WechatPage } from './pages/WechatPage'
import { AutomationPage } from './pages/AutomationPage'
import { SettingsPage } from './pages/SettingsPage'
import { useAppStore } from './stores/appStore'
import { useWebSocket } from './hooks/useWebSocket'

function App() {
  useWebSocket()
  const { activeTab } = useAppStore()

  const renderPage = () => {
    switch (activeTab) {
      case 'search': return <SearchPage />
      case 'applications': return <ApplicationsPage />
      case 'chat': return <ChatPage />
      case 'wechat': return <WechatPage />
      case 'automation': return <AutomationPage />
      case 'settings': return <SettingsPage />
      default: return <SearchPage />
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">
        <PageHeader />
        {renderPage()}
      </main>
      <ToastContainer />
    </div>
  )
}

export default App