const API_BASE = '/api'

export interface Repository {
  id: number
  url: string
  name: string
  owner: string
  branch: string
  commit_sha: string | null
  description: string | null
  status: string
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface RepositoryStats {
  total_files: number
  total_source_files: number
  total_functions: number
  total_classes: number
  total_imports: number
  total_exports: number
  total_calls: number
  languages: Record<string, number>
  frameworks: string[]
}

export interface RepositoryFile {
  id: number
  path: string
  language: string | null
  size_bytes: number
  category: string
  has_syntax_errors: boolean
  entity_count: number
  import_count: number
  export_count: number
  call_count: number
  content?: string
  symbols?: Symbol[]
}

export interface Symbol {
  id: number
  name: string
  qualified_name: string | null
  symbol_type: string
  file_path: string | null
  start_line: number | null
  end_line: number | null
  parameters: string[]
  metadata: Record<string, any>
}

export interface GraphNode {
  node_id: string
  node_type: string
  name: string
  file_path: string | null
  qualified_name: string | null
  metadata: Record<string, any>
}

export interface GraphEdge {
  source_id: string
  target_id: string
  edge_type: string
  metadata: Record<string, any>
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: Record<string, number>
}

export interface AnalysisLevel {
  level: string
  project_overview: string
  technology_explanation: string
  repository_structure: string
  basic_flow: string
  learning_path: string
  architecture: string
  modules: string
  data_flow: string
  dependencies: string
  important_functions: string
  function_analysis: string
  call_graph: string
  dependency_graph: string
  complexity: string
  security: string
  api_surface: string
  entry_points: string[]
  call_graph_summary: string
  coupling_analysis: string
  dead_code_candidates: string
  security_observations: string
  circular_dependencies: string
}

export interface QuestionResponse {
  question: string
  answer: string
  evidence: any[]
  confidence: number
  related_files: string[]
  related_symbols: string[]
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const api = {
  analyze: (url: string) =>
    request<Repository>('/repositories/analyze', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),

  getRepository: (id: number) =>
    request<Repository>(`/repositories/${id}`),

  getStats: (id: number) =>
    request<RepositoryStats>(`/repositories/${id}/stats`),

  getFiles: (id: number) =>
    request<RepositoryFile[]>(`/repositories/${id}/files`),

  getFile: (repoId: number, fileId: number) =>
    request<RepositoryFile>(`/repositories/${repoId}/files/${fileId}`),

  getSymbols: (id: number, type?: string) =>
    request<Symbol[]>(`/repositories/${id}/symbols${type ? `?symbol_type=${type}` : ''}`),

  getAnalysis: (id: number, level: string) =>
    request<AnalysisLevel>(`/repositories/${id}/analysis/${level}`),

  getGraph: (id: number, nodeType?: string, edgeType?: string) => {
    const params = new URLSearchParams()
    if (nodeType) params.set('node_type', nodeType)
    if (edgeType) params.set('edge_type', edgeType)
    const qs = params.toString()
    return request<GraphData>(`/repositories/${id}/graph${qs ? `?${qs}` : ''}`)
  },

  askQuestion: (id: number, question: string) =>
    request<QuestionResponse>(`/repositories/${id}/questions`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),

  generateReport: (id: number) =>
    fetch(`${API_BASE}/repositories/${id}/report`, { method: 'POST' })
      .then(res => res.text()),

  deleteRepository: (id: number) =>
    request(`/repositories/${id}`, { method: 'DELETE' }),
}
