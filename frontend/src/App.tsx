import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import RepositoryPage from './pages/RepositoryPage'
import AnalysisPage from './pages/AnalysisPage'
import FilesPage from './pages/FilesPage'
import GraphPage from './pages/GraphPage'
import AssistantPage from './pages/AssistantPage'
import ReportPage from './pages/ReportPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/repository/:id" element={<Layout />}>
        <Route index element={<RepositoryPage />} />
        <Route path="beginner" element={<AnalysisPage level="beginner" />} />
        <Route path="intermediate" element={<AnalysisPage level="intermediate" />} />
        <Route path="advanced" element={<AnalysisPage level="advanced" />} />
        <Route path="files" element={<FilesPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route path="assistant" element={<AssistantPage />} />
        <Route path="report" element={<ReportPage />} />
      </Route>
    </Routes>
  )
}

export default App
