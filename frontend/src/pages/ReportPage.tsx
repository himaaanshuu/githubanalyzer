import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { FileText, Loader2, Download, Copy, Check } from 'lucide-react'
import { api } from '../lib/api'

export default function ReportPage() {
  const { id } = useParams()
  const [report, setReport] = useState('')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const generateReport = async () => {
    if (!id) return
    setLoading(true)
    try {
      const content = await api.generateReport(Number(id))
      setReport(content)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = async () => {
    await navigator.clipboard.writeText(report)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const blob = new Blob([report], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'github-intelligence-report.md'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Project Report</h1>
          <p className="text-gray-400 text-sm">Generate comprehensive documentation for this repository.</p>
        </div>
        <div className="flex gap-2">
          {!report ? (
            <button onClick={generateReport} disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
              {loading ? 'Generating...' : 'Generate Report'}
            </button>
          ) : (
            <>
              <button onClick={handleCopy} className="btn-secondary">
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied!' : 'Copy'}
              </button>
              <button onClick={handleDownload} className="btn-primary">
                <Download className="w-4 h-4" />
                Download .md
              </button>
            </>
          )}
        </div>
      </div>

      {report ? (
        <div className="card">
          <pre className="whitespace-pre-wrap text-sm text-gray-300 font-mono leading-relaxed">
            {report}
          </pre>
        </div>
      ) : !loading ? (
        <div className="card text-center py-16">
          <FileText className="w-12 h-12 mx-auto mb-4 text-gray-600" />
          <p className="text-gray-400 mb-4">Click "Generate Report" to create comprehensive project documentation.</p>
          <p className="text-sm text-gray-500">The report includes architecture analysis, code relationships, and learning guides.</p>
        </div>
      ) : (
        <div className="card text-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-brand-500 mx-auto mb-4" />
          <p className="text-gray-400">Generating report...</p>
        </div>
      )}
    </div>
  )
}
