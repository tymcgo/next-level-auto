'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/', label: 'Dashboard', icon: '📊' },
  { href: '/ro', label: 'Repair Orders', icon: '🔧' },
  { href: '/estimates', label: 'Estimates', icon: '📝' },
  { href: '/inventory', label: 'Inventory', icon: '📦' },
  { href: '/lot', label: 'Buy/Sell Lot', icon: '🚗' },
  { href: '/subscriptions', label: 'Subscriptions', icon: '💳' },
  { href: '/credits', label: 'Customer Credits', icon: '🎁' },
  { href: '/audit', label: 'Audit Log', icon: '📋' },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-xl font-bold text-blue-400">Next Level Auto</h1>
        <p className="text-xs text-gray-500 mt-1">Agentic Shop System</p>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map((item) => {
          const active = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          )
        })}
      </nav>
      <div className="p-4 border-t border-gray-800 text-xs text-gray-600">
        v1.0.0 • TEST Mode
      </div>
    </aside>
  )
}
