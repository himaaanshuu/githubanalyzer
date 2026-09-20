import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GitBranch, Search, Github, ArrowRight, Loader2, Code, Network, Brain, FileText } from 'lucide-react'
import { api } from '../lib/api'

export default function HomePage() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleAnalyze = async () => {
    if (!url.trim()) return
    setLoading(true)
    setError('')
    try {
      const repo = await api.analyze(url.trim())
      navigate(`/repository/${repo.id}`)
    } catch (err: any) {
      setError(err.message || 'Failed to analyze repository')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  const features = [
    { icon: Code, title: 'Deep Code Analysis', desc: 'AST parsing, symbol extraction, and call graph analysis across multiple languages' },
    { icon: Network, title: 'Architecture Detection', desc: 'Automatic identification of MVC, layered, and component-based architectures' },
    { icon: Brain, title: 'Three-Level Explanations', desc: 'Understand any codebase from Beginner to Advanced with progressive depth' },
    { icon: FileText, title: 'Project Reports', desc: 'Generate comprehensive documentation with just one click' },
  ]

  return (
    <div className="min-h-screen bg-dark-0">
      {/* Header */}
      <header className="border-b border-dark-3 bg-dark-1/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-brand-600 rounded-lg flex items-center justify-center">
              <GitBranch className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-semibold text-white">GitHub Intelligence</span>
          </div>
          <div className="text-sm text-gray-500">Understand Any Codebase</div>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 rounded-full px-4 py-1.5 mb-6">
          <span className="text-brand-400 text-sm font-medium">AI-Powered Repository Analysis</span>
        </div>

        <h1 className="text-5xl font-bold text-white mb-6 leading-tight">
          Understand Any<br />GitHub Repository
        </h1>

        <p className="text-lg text-gray-400 mb-10 max-w-2xl mx-auto leading-relaxed">
          Paste a repository URL and get a complete AI-powered explanation of its architecture,
          code, functions, dependencies, and execution flow — from beginner to advanced.
        </p>

        {/* Input */}
        <div className="max-w-2xl mx-auto">
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Github className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="https://github.com/username/repository"
                className="input-field pl-12 py-4 text-base"
                disabled={loading}
              />
            </div>
            <button
              onClick={handleAnalyze}
              disabled={loading || !url.trim()}
              className="btn-primary px-8 py-4 text-base disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  Analyze
                  <ArrowRight className="w-5 h-5" />
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-6 pb-20">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {features.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card-hover">
              <div className="w-10 h-10 bg-brand-500/10 rounded-lg flex items-center justify-center mb-4">
                <Icon className="w-5 h-5 text-brand-400" />
              </div>
              <h3 className="text-white font-semibold mb-2">{title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-dark-3 py-8">
        <div className="max-w-6xl mx-auto px-6 text-center text-sm text-gray-500">
          GitHub Intelligence — Understand Any Codebase. From Beginner to Expert.
        </div>
      </footer>
    </div>
  )
}
