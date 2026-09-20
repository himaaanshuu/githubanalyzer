import { Outlet, NavLink, useParams } from 'react-router-dom'
import { GitBranch, BarChart3, FileCode, Network, MessageSquare, FileText, Layers, BookOpen, GraduationCap, Zap } from 'lucide-react'

const navItems = [
  { to: '', icon: BarChart3, label: 'Overview' },
  { to: 'beginner', icon: BookOpen, label: 'Beginner' },
  { to: 'intermediate', icon: Layers, label: 'Intermediate' },
  { to: 'advanced', icon: Zap, label: 'Advanced' },
  { to: 'files', icon: FileCode, label: 'Files' },
  { to: 'graph', icon: Network, label: 'Code Graph' },
  { to: 'assistant', icon: MessageSquare, label: 'AI Assistant' },
  { to: 'report', icon: FileText, label: 'Report' },
]

export default function Layout() {
  const { id } = useParams()

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-dark-1 border-r border-dark-3 flex flex-col">
        {/* Logo */}
        <div className="p-4 border-b border-dark-3">
          <NavLink to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
              <GitBranch className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold text-white">GitHub Intelligence</span>
          </NavLink>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={`/repository/${id}/${to}`}
              end={to === ''}
              className={({ isActive }) =>
                isActive ? 'sidebar-link-active' : 'sidebar-link'
              }
            >
              <Icon className="w-4 h-4" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-3 border-t border-dark-3">
          <NavLink to="/" className="sidebar-link text-gray-500">
            <span className="text-sm">Back to Home</span>
          </NavLink>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
