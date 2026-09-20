import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { BookOpen, Layers, Zap, Loader2 } from 'lucide-react'
import { api, AnalysisLevel } from '../lib/api'

const LEVEL_CONFIG = {
  beginner: { icon: BookOpen, title: 'Beginner Level', color: 'green' },
  intermediate: { icon: Layers, title: 'Intermediate Level', color: 'blue' },
  advanced: { icon: Zap, title: 'Advanced Level', color: 'purple' },
}

export default function AnalysisPage({ level }: { level: string }) {
  const { id } = useParams()
  const [data, setData] = useState<AnalysisLevel | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    api.getAnalysis(Number(id), level)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id, level])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
      </div>
    )
  }

  if (!data) {
    return <div className="text-center py-20 text-gray-400">No analysis available</div>
  }

  const config = LEVEL_CONFIG[level as keyof typeof LEVEL_CONFIG]
  const Icon = config?.icon || BookOpen

  const sections = getSectionsForLevel(level, data)

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-brand-500/10 rounded-lg flex items-center justify-center">
          <Icon className="w-5 h-5 text-brand-400" />
        </div>
        <h1 className="text-2xl font-bold text-white">{config?.title || level}</h1>
      </div>

      {sections.map(({ title, content, id: sectionId }) => (
        content ? (
          <div key={sectionId} className="card">
            <h2 className="text-lg font-semibold text-white mb-3">{title}</h2>
            <div className="text-gray-300 leading-relaxed whitespace-pre-wrap text-sm">
              {content}
            </div>
          </div>
        ) : null
      ))}
    </div>
  )
}

function getSectionsForLevel(level: string, data: AnalysisLevel) {
  if (level === 'beginner') {
    return [
      { id: 'overview', title: 'What does this project do?', content: data.project_overview },
      { id: 'tech', title: 'Technology Explanation', content: data.technology_explanation },
      { id: 'structure', title: 'Repository Structure', content: data.repository_structure },
      { id: 'flow', title: 'Basic Flow', content: data.basic_flow },
      { id: 'learning', title: 'Learning Path', content: data.learning_path },
    ]
  }
  if (level === 'intermediate') {
    return [
      { id: 'arch', title: 'Architecture', content: data.architecture },
      { id: 'modules', title: 'Modules', content: data.modules },
      { id: 'api', title: 'API Surface', content: data.api_surface },
      { id: 'flow', title: 'Data Flow', content: data.data_flow },
      { id: 'deps', title: 'Dependencies', content: data.dependencies },
      { id: 'important', title: 'Important Functions', content: data.important_functions },
    ]
  }
  return [
    { id: 'complexity', title: 'Complexity Analysis', content: data.complexity },
    { id: 'calls', title: 'Call Graph Summary', content: data.call_graph_summary || data.call_graph },
    { id: 'coupling', title: 'Coupling Analysis', content: data.coupling_analysis },
    { id: 'dead-code', title: 'Dead Code Candidates', content: data.dead_code_candidates },
    { id: 'circular', title: 'Circular Dependencies', content: data.circular_dependencies },
    { id: 'security', title: 'Security Observations', content: data.security_observations || data.security },
  ]
}
