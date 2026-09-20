import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { MessageSquare, Send, Loader2, FileCode, AlertCircle } from 'lucide-react'
import { api, QuestionResponse } from '../lib/api'

const SUGGESTED_QUESTIONS = [
  'How does authentication work?',
  'What is the main entry point?',
  'How are API routes organized?',
  'What database models exist?',
  'How does error handling work?',
  'What are the main dependencies?',
]

export default function AssistantPage() {
  const { id } = useParams()
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<QuestionResponse[]>([])

  const handleAsk = async (q?: string) => {
    const text = q || question.trim()
    if (!text || !id) return
    setLoading(true)
    setQuestion('')
    try {
      const response = await api.askQuestion(Number(id), text)
      setHistory(prev => [response, ...prev])
    } catch (err: any) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleAsk()
    }
  }

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-3rem)] flex flex-col">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-2">AI Assistant</h1>
        <p className="text-gray-400 text-sm">Ask questions about the repository and get evidence-based answers.</p>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {history.length === 0 && !loading && (
          <div className="text-center py-12">
            <MessageSquare className="w-12 h-12 mx-auto mb-4 text-gray-600" />
            <p className="text-gray-400 mb-6">Ask a question about the codebase</p>
            <div className="grid grid-cols-2 gap-2 max-w-lg mx-auto">
              {SUGGESTED_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => handleAsk(q)}
                  className="text-left px-4 py-3 bg-dark-1 border border-dark-3 rounded-lg text-sm text-gray-300 hover:border-brand-500/50 hover:bg-dark-2 transition-all"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {history.map((item, i) => (
          <div key={i} className="space-y-3">
            {/* Question */}
            <div className="flex justify-end">
              <div className="bg-brand-600 text-white px-4 py-2 rounded-2xl rounded-br-sm max-w-[80%] text-sm">
                {item.question}
              </div>
            </div>

            {/* Answer */}
            <div className="flex justify-start">
              <div className="bg-dark-1 border border-dark-3 px-4 py-3 rounded-2xl rounded-bl-sm max-w-[80%]">
                <div className="text-sm text-gray-200 whitespace-pre-wrap">{item.answer}</div>

                {/* Evidence */}
                {item.evidence.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-dark-3">
                    <div className="text-xs text-gray-500 mb-2">Evidence:</div>
                    <div className="space-y-1">
                      {item.evidence.slice(0, 5).map((ev, j) => (
                        <div key={j} className="flex items-center gap-2 text-xs">
                          <FileCode className="w-3 h-3 text-gray-500" />
                          <span className="text-gray-400">{ev.name}</span>
                          <span className="text-gray-500">{ev.symbol_type}</span>
                          {ev.file && <span className="text-gray-500 font-mono">{ev.file}:{ev.line}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Confidence */}
                <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                  <AlertCircle className="w-3 h-3" />
                  Confidence: {Math.round(item.confidence * 100)}%
                </div>

                {/* Related Files */}
                {item.related_files.length > 0 && (
                  <div className="mt-2 text-xs text-gray-500">
                    Related: {item.related_files.slice(0, 5).join(', ')}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-dark-1 border border-dark-3 px-4 py-3 rounded-2xl rounded-bl-sm">
              <Loader2 className="w-5 h-5 animate-spin text-brand-400" />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-3">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the codebase..."
          className="input-field flex-1"
          disabled={loading}
        />
        <button
          onClick={() => handleAsk()}
          disabled={loading || !question.trim()}
          className="btn-primary px-6 disabled:opacity-50"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
