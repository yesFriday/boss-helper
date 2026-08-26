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

  const isFullHeightPage = activeTab === 'chat'

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
      <main className="flex-1 flex flex-col min-h-0 p-6">
        <PageHeader />
        {isFullHeightPage ? (
          <div className="flex-1 min-h-0 flex flex-col">{renderPage()}</div>
        ) : (
          <div className="flex-1 min-h-0 overflow-y-auto pr-1 -mr-1">{renderPage()}</div>
        )}
      </main>
      <ToastContainer />
    </div>
  )
}

export default App
