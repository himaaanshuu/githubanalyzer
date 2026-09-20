import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { GitBranch, Users, FileCode, FunctionSquare, Import, Download, Phone, Loader2, RefreshCw } from 'lucide-react'
import { api, Repository, RepositoryStats } from '../lib/api'

const STATUS_LABELS: Record<string, string> = {
  pending: 'Queued',
  cloning: 'Cloning Repository',
  scanning: 'Scanning Files',
  parsing: 'Parsing Code',
  building_graph: 'Building Code Graph',
  analyzing: 'Analyzing Architecture',
  completed: 'Analysis Complete',
  failed: 'Analysis Failed',
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'text-gray-400',
  cloning: 'text-yellow-400',
  scanning: 'text-blue-400',
  parsing: 'text-blue-400',
  building_graph: 'text-purple-400',
  analyzing: 'text-purple-400',
  completed: 'text-green-400',
  failed: 'text-red-400',
}

export default function RepositoryPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [repo, setRepo] = useState<Repository | null>(null)
  const [stats, setStats] = useState<RepositoryStats | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    if (!id) return
    try {
      const repoData = await api.getRepository(Number(id))
      setRepo(repoData)
      if (repoData.status === 'completed') {
        const statsData = await api.getStats(Number(id))
        setStats(statsData)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [id])

  // Poll for status updates while analyzing
  useEffect(() => {
    if (!repo || repo.status === 'completed' || repo.status === 'failed') return
    const interval = setInterval(fetchData, 2000)
    return () => clearInterval(interval)
  }, [repo?.status])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
      </div>
    )
  }

  if (!repo) {
    return <div className="text-center py-20 text-gray-400">Repository not found</div>
  }

  const isAnalyzing = !['completed', 'failed'].includes(repo.status)

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">{repo.name}</h1>
          <p className="text-gray-400">
            {repo.owner} / {repo.name}
            <span className="ml-3 text-sm text-gray-500">
              <GitBranch className="w-3.5 h-3.5 inline mr-1" />
              {repo.branch}
              {repo.commit_sha && <span className="ml-2 font-mono text-xs">{repo.commit_sha}</span>}
            </span>
          </p>
        </div>
        <div className={`text-sm font-medium ${STATUS_COLORS[repo.status]}`}>
          {isAnalyzing && <Loader2 className="w-4 h-4 inline mr-2 animate-spin" />}
          {STATUS_LABELS[repo.status] || repo.status}
        </div>
      </div>

      {/* Progress Steps (while analyzing) */}
      {isAnalyzing && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Analysis Progress</h3>
          <div className="space-y-3">
            {['cloning', 'scanning', 'parsing', 'building_graph', 'analyzing', 'completed'].map((step, i) => {
              const stepIndex = ['cloning', 'scanning', 'parsing', 'building_graph', 'analyzing', 'completed'].indexOf(repo.status)
              const isComplete = i < stepIndex
              const isCurrent = i === stepIndex
              return (
                <div key={step} className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                    isComplete ? 'bg-green-500/20 text-green-400' :
                    isCurrent ? 'bg-brand-500/20 text-brand-400' :
                    'bg-dark-3 text-gray-500'
                  }`}>
                    {isComplete ? '✓' : i + 1}
                  </div>
                  <span className={`text-sm ${isCurrent ? 'text-white' : isComplete ? 'text-gray-400' : 'text-gray-500'}`}>
                    {STATUS_LABELS[step]}
                  </span>
                  {isCurrent && <Loader2 className="w-4 h-4 text-brand-400 animate-spin" />}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Error */}
      {repo.status === 'failed' && repo.error_message && (
        <div className="card border-red-500/30 bg-red-500/5">
          <h3 className="text-red-400 font-medium mb-2">Analysis Failed</h3>
          <p className="text-sm text-red-300/80">{repo.error_message}</p>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <StatCard icon={FileCode} label="Files" value={stats.total_files} />
          <StatCard icon={FunctionSquare} label="Functions" value={stats.total_functions} />
          <StatCard icon={Users} label="Classes" value={stats.total_classes} />
          <StatCard icon={Import} label="Imports" value={stats.total_imports} />
          <StatCard icon={Download} label="Exports" value={stats.total_exports} />
          <StatCard icon={Phone} label="Calls" value={stats.total_calls} />
          <StatCard icon={GitBranch} label="Languages" value={Object.keys(stats.languages).length} />
        </div>
      )}

      {/* Languages & Frameworks */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Languages</h3>
            <div className="space-y-2">
              {Object.entries(stats.languages).sort((a, b) => b[1] - a[1]).map(([lang, count]) => (
                <div key={lang} className="flex items-center justify-between">
                  <span className="text-sm text-gray-200">{lang}</span>
                  <span className="text-sm text-gray-400 font-mono">{count} files</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Frameworks</h3>
            {stats.frameworks.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {stats.frameworks.map(f => (
                  <span key={f} className="badge bg-brand-500/10 text-brand-400 border border-brand-500/20">{f}</span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">No frameworks detected</p>
            )}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      {repo.status === 'completed' && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <button onClick={() => navigate(`/repository/${id}/beginner`)} className="card-hover text-left">
            <div className="text-lg font-semibold text-white mb-1">Beginner</div>
            <div className="text-sm text-gray-400">Start here if you're new</div>
          </button>
          <button onClick={() => navigate(`/repository/${id}/intermediate`)} className="card-hover text-left">
            <div className="text-lg font-semibold text-white mb-1">Intermediate</div>
            <div className="text-sm text-gray-400">Architecture & modules</div>
          </button>
          <button onClick={() => navigate(`/repository/${id}/advanced`)} className="card-hover text-left">
            <div className="text-lg font-semibold text-white mb-1">Advanced</div>
            <div className="text-sm text-gray-400">Deep code analysis</div>
          </button>
          <button onClick={() => navigate(`/repository/${id}/graph`)} className="card-hover text-left">
            <div className="text-lg font-semibold text-white mb-1">Code Graph</div>
            <div className="text-sm text-gray-400">Visual relationships</div>
          </button>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value }: { icon: any; label: string; value: number }) {
  return (
    <div className="stat-card">
      <Icon className="w-4 h-4 text-gray-500 mb-2" />
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}
