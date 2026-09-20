import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Filter, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { api, GraphData, GraphNode } from '../lib/api'

export default function GraphPage() {
  const { id } = useParams()
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!id) return
    api.getGraph(Number(id))
      .then(setGraph)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    if (!graph || !svgRef.current) return
    renderGraph(graph, filter, setSelectedNode)
  }, [graph, filter])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
      </div>
    )
  }

  if (!graph) {
    return <div className="text-center py-20 text-gray-400">No graph data available</div>
  }

  const nodeTypes = [...new Set(graph.nodes.map(n => n.node_type))]

  return (
    <div className="flex gap-4 h-[calc(100vh-3rem)]">
      {/* Controls */}
      <div className="w-64 flex-shrink-0 bg-dark-1 border border-dark-3 rounded-xl p-4 overflow-y-auto">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Filters</h3>
        <div className="space-y-1">
          <button
            onClick={() => setFilter('all')}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm ${filter === 'all' ? 'bg-brand-500/10 text-brand-400' : 'text-gray-400 hover:bg-dark-2'}`}
          >
            All Nodes ({graph.nodes.length})
          </button>
          {nodeTypes.map(type => (
            <button
              key={type}
              onClick={() => setFilter(type)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm ${filter === type ? 'bg-brand-500/10 text-brand-400' : 'text-gray-400 hover:bg-dark-2'}`}
            >
              {type} ({graph.nodes.filter(n => n.node_type === type).length})
            </button>
          ))}
        </div>

        {/* Stats */}
        <div className="mt-6 space-y-2">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Graph Stats</h3>
          {Object.entries(graph.stats).map(([key, count]) => (
            <div key={key} className="flex justify-between text-xs">
              <span className="text-gray-400">{key}</span>
              <span className="text-gray-300 font-mono">{count}</span>
            </div>
          ))}
        </div>

        {/* Selected Node */}
        {selectedNode && (
          <div className="mt-6">
            <h3 className="text-sm font-medium text-gray-400 mb-2">Selected Node</h3>
            <div className="bg-dark-2 rounded-lg p-3 text-sm">
              <div className="text-white font-medium">{selectedNode.name}</div>
              <div className="text-gray-400 text-xs mt-1">{selectedNode.node_type}</div>
              {selectedNode.file_path && (
                <div className="text-gray-500 text-xs mt-1 font-mono">{selectedNode.file_path}</div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Graph */}
      <div className="flex-1 bg-dark-1 border border-dark-3 rounded-xl overflow-hidden relative">
        <svg ref={svgRef} className="w-full h-full" />
        <div className="absolute bottom-4 right-4 flex gap-2">
          <button className="p-2 bg-dark-2 rounded-lg border border-dark-3 hover:bg-dark-3">
            <ZoomIn className="w-4 h-4 text-gray-400" />
          </button>
          <button className="p-2 bg-dark-2 rounded-lg border border-dark-3 hover:bg-dark-3">
            <ZoomOut className="w-4 h-4 text-gray-400" />
          </button>
          <button className="p-2 bg-dark-2 rounded-lg border border-dark-3 hover:bg-dark-3">
            <Maximize2 className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>
    </div>
  )
}

const NODE_COLORS: Record<string, string> = {
  file: '#748ffc',
  function: '#51cf66',
  method: '#51cf66',
  class: '#cc5de8',
  component: '#ff922b',
  external_module: '#868e96',
  variable: '#fcc419',
  repository: '#20c997',
  api_endpoint: '#ff6b6b',
  database_model: '#f06595',
}

const EDGE_COLORS: Record<string, string> = {
  imports: '#4c6ef5',
  calls: '#51cf66',
  contains: '#868e96',
  exports: '#fcc419',
  depends_on: '#ff922b',
}

function renderGraph(
  graph: GraphData,
  filter: string,
  onNodeClick: (node: GraphNode) => void,
) {
  const svg = document.querySelector('svg')
  if (!svg) return

  const width = svg.clientWidth || 800
  const height = svg.clientHeight || 600

  // Clear
  svg.innerHTML = ''

  const nodes = filter === 'all' ? graph.nodes : graph.nodes.filter(n => n.node_type === filter)
  const nodeIds = new Set(nodes.map(n => n.node_id))
  const edges = graph.edges.filter(e => nodeIds.has(e.source_id) && nodeIds.has(e.target_id))

  // Simple force-directed layout (basic spring physics)
  const nodeMap = new Map(nodes.map((n, i) => [n.node_id, {
    ...n,
    x: width / 2 + (Math.random() - 0.5) * 300,
    y: height / 2 + (Math.random() - 0.5) * 300,
    vx: 0,
    vy: 0,
  }]))

  // Simple force simulation
  for (let iter = 0; iter < 100; iter++) {
    // Repulsion
    for (const [, a] of nodeMap) {
      for (const [, b] of nodeMap) {
        if (a === b) continue
        const dx = a.x - b.x
        const dy = a.y - b.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = 500 / (dist * dist)
        a.vx += (dx / dist) * force
        a.vy += (dy / dist) * force
      }
    }

    // Attraction (edges)
    for (const edge of edges) {
      const a = nodeMap.get(edge.source_id)
      const b = nodeMap.get(edge.target_id)
      if (!a || !b) continue
      const dx = b.x - a.x
      const dy = b.y - a.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = (dist - 100) * 0.01
      a.vx += (dx / dist) * force
      a.vy += (dy / dist) * force
      b.vx -= (dx / dist) * force
      b.vy -= (dy / dist) * force
    }

    // Center gravity
    for (const [, node] of nodeMap) {
      node.vx += (width / 2 - node.x) * 0.001
      node.vy += (height / 2 - node.y) * 0.001
      node.x += node.vx * 0.3
      node.y += node.vy * 0.3
      node.vx *= 0.9
      node.vy *= 0.9
      // Bounds
      node.x = Math.max(50, Math.min(width - 50, node.x))
      node.y = Math.max(50, Math.min(height - 50, node.y))
    }
  }

  // Draw edges
  const edgeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')
  for (const edge of edges) {
    const source = nodeMap.get(edge.source_id)
    const target = nodeMap.get(edge.target_id)
    if (!source || !target) continue

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
    line.setAttribute('x1', String(source.x))
    line.setAttribute('y1', String(source.y))
    line.setAttribute('x2', String(target.x))
    line.setAttribute('y2', String(target.y))
    line.setAttribute('stroke', EDGE_COLORS[edge.edge_type] || '#46494f')
    line.setAttribute('stroke-width', '1')
    line.setAttribute('stroke-opacity', '0.4')
    edgeGroup.appendChild(line)
  }
  svg.appendChild(edgeGroup)

  // Draw nodes
  const nodeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')
  for (const [, node] of nodeMap) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    g.style.cursor = 'pointer'

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
    const radius = node.node_type === 'file' ? 6 : node.node_type === 'class' ? 8 : 5
    circle.setAttribute('cx', String(node.x))
    circle.setAttribute('cy', String(node.y))
    circle.setAttribute('r', String(radius))
    circle.setAttribute('fill', NODE_COLORS[node.node_type] || '#868e96')
    circle.setAttribute('stroke', '#1a1b1e')
    circle.setAttribute('stroke-width', '2')
    g.appendChild(circle)

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    text.setAttribute('x', String(node.x))
    text.setAttribute('y', String(node.y + radius + 12))
    text.setAttribute('text-anchor', 'middle')
    text.setAttribute('fill', '#adb5bd')
    text.setAttribute('font-size', '10')
    text.setAttribute('font-family', 'Inter, sans-serif')
    text.textContent = node.name.length > 20 ? node.name.slice(0, 18) + '...' : node.name
    g.appendChild(text)

    g.addEventListener('click', () => onNodeClick(node))
    g.addEventListener('mouseenter', () => {
      circle.setAttribute('r', String(radius + 2))
      circle.setAttribute('stroke', '#5c7cfa')
    })
    g.addEventListener('mouseleave', () => {
      circle.setAttribute('r', String(radius))
      circle.setAttribute('stroke', '#1a1b1e')
    })

    nodeGroup.appendChild(g)
  }
  svg.appendChild(nodeGroup)
}
