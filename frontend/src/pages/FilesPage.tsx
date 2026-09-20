import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { FileCode, Loader2, ChevronRight, ChevronDown, Search } from 'lucide-react'
import { api, RepositoryFile, Symbol } from '../lib/api'

export default function FilesPage() {
  const { id } = useParams()
  const [files, setFiles] = useState<RepositoryFile[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState<RepositoryFile | null>(null)
  const [symbols, setSymbols] = useState<Symbol[]>([])
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!id) return
    api.getFiles(Number(id))
      .then(setFiles)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id])

  const handleFileClick = async (file: RepositoryFile) => {
    setSelectedFile(file)
    if (id) {
      try {
        const detail = await api.getFile(Number(id), file.id)
        setSelectedFile(detail)
        setSymbols(detail.symbols || [])
      } catch (err) {
        console.error(err)
      }
    }
  }

  const filteredFiles = files.filter(f =>
    f.path.toLowerCase().includes(search.toLowerCase())
  )

  // Build tree structure
  const tree = buildTree(filteredFiles)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
      </div>
    )
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-3rem)]">
      {/* File Tree */}
      <div className="w-80 flex-shrink-0 bg-dark-1 border border-dark-3 rounded-xl overflow-hidden flex flex-col">
        <div className="p-3 border-b border-dark-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search files..."
              className="input-field pl-9 py-2 text-xs"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <TreeNode
            tree={tree}
            selectedFile={selectedFile}
            onFileClick={handleFileClick}
            level={0}
          />
        </div>
      </div>

      {/* File Detail */}
      <div className="flex-1 bg-dark-1 border border-dark-3 rounded-xl overflow-hidden flex flex-col">
        {selectedFile ? (
          <>
            <div className="p-4 border-b border-dark-3 flex items-center justify-between">
              <div>
                <h3 className="text-white font-mono text-sm">{selectedFile.path}</h3>
                <div className="flex gap-4 mt-1 text-xs text-gray-400">
                  {selectedFile.language && <span>{selectedFile.language}</span>}
                  <span>{symbols.length} symbols</span>
                  <span>{selectedFile.import_count} imports</span>
                  <span>{selectedFile.call_count} calls</span>
                </div>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {/* Symbols */}
              {symbols.length > 0 && (
                <div className="mb-6">
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Symbols</h4>
                  <div className="space-y-1">
                    {symbols.map(sym => (
                      <div key={sym.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-dark-2 hover:bg-dark-3 transition-colors">
                        <span className={`w-2 h-2 rounded-full ${
                          sym.symbol_type === 'function' ? 'bg-blue-400' :
                          sym.symbol_type === 'class' ? 'bg-purple-400' :
                          sym.symbol_type === 'method' ? 'bg-green-400' :
                          'bg-gray-400'
                        }`} />
                        <span className="text-sm text-gray-200 font-mono">{sym.name}</span>
                        <span className="text-xs text-gray-500">{sym.symbol_type}</span>
                        {sym.start_line && (
                          <span className="text-xs text-gray-500 ml-auto">L{sym.start_line}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* File Content */}
              {selectedFile.content && (
                <div>
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Source Code</h4>
                  <pre className="code-block overflow-x-auto">
                    <code>{selectedFile.content}</code>
                  </pre>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <FileCode className="w-12 h-12 mx-auto mb-3 text-gray-600" />
              <p>Select a file to view its details</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Tree data structure
interface TreeNode {
  name: string
  path: string
  isFile: boolean
  file?: RepositoryFile
  children: Record<string, TreeNode>
}

function buildTree(files: RepositoryFile[]): TreeNode {
  const root: TreeNode = { name: '', path: '', isFile: false, children: {} }

  for (const file of files) {
    const parts = file.path.split('/')
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          path: parts.slice(0, i + 1).join('/'),
          isFile: i === parts.length - 1,
          children: {},
        }
      }
      if (i === parts.length - 1) {
        current.children[part].file = file
      }
      current = current.children[part]
    }
  }

  return root
}

function TreeNode({ tree, selectedFile, onFileClick, level }: {
  tree: TreeNode
  selectedFile: RepositoryFile | null
  onFileClick: (file: RepositoryFile) => void
  level: number
}) {
  const [expanded, setExpanded] = useState(level < 1)
  const entries = Object.values(tree.children).sort((a, b) => {
    if (a.isFile !== b.isFile) return a.isFile ? 1 : -1
    return a.name.localeCompare(b.name)
  })

  return (
    <div>
      {entries.map(entry => (
        entry.isFile ? (
          <div
            key={entry.path}
            onClick={() => entry.file && onFileClick(entry.file)}
            className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-sm ${
              selectedFile?.path === entry.path
                ? 'bg-brand-500/10 text-brand-400'
                : 'text-gray-400 hover:text-gray-200 hover:bg-dark-2'
            }`}
            style={{ paddingLeft: `${level * 16 + 8}px` }}
          >
            <FileCode className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="truncate font-mono text-xs">{entry.name}</span>
          </div>
        ) : (
          <div key={entry.path}>
            <div
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-sm text-gray-300 hover:bg-dark-2"
              style={{ paddingLeft: `${level * 16 + 8}px` }}
            >
              {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              <span className="font-mono text-xs">{entry.name}</span>
            </div>
            {expanded && (
              <TreeNode
                tree={entry}
                selectedFile={selectedFile}
                onFileClick={onFileClick}
                level={level + 1}
              />
            )}
          </div>
        )
      ))}
    </div>
  )
}
