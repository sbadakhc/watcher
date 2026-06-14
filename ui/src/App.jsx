import { useState } from 'react'
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom'
import Storefront from './components/Storefront'
import SubmitForm from './components/SubmitForm'
import ReviewQueue from './components/ReviewQueue'
import LoginModal from './components/LoginModal'
import UserDashboard from './components/UserDashboard'

// Brand colors
const COLORS = {
  primary: '#6366f1',
  primaryDark: '#4f46e5',
  secondary: '#8b5cf6',
  accent: '#06b6d4',
  success: '#22c55e',
  danger: '#ef4444',
  warning: '#f59e0b',
  dark: '#0f172a',
  gray: '#64748b',
  lightGray: '#f1f5f9',
  white: '#ffffff'
}

function AppContent() {
  const [user, setUser] = useState(null)
  const navigate = useNavigate()

  const handleLogin = (userData) => {
    setUser(userData)
    if (userData.is_admin) {
      navigate('/review')
    } else {
      navigate('/submit')
    }
  }

  const handleLogout = () => {
    setUser(null)
    navigate('/')
  }

  return (
    <div style={{ minHeight: '100vh', background: COLORS.lightGray, fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }}>
      {/* Navbar */}
      <nav style={{
        background: COLORS.white,
        color: COLORS.dark,
        padding: '0 2rem',
        height: '64px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)',
        position: 'sticky',
        top: 0,
        zIndex: 100
      }}>
        <Link to="/" style={{ color: COLORS.dark, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            width: '40px',
            height: '40px',
            background: `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.secondary} 100%)`,
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.5rem'
          }}>
            🏪
          </div>
          <div>
            <div style={{ fontSize: '1.25rem', fontWeight: '800', letterSpacing: '-0.025em', color: COLORS.dark }}>Cashi Shop</div>
            <div style={{ fontSize: '0.75rem', color: COLORS.gray, fontWeight: '500', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Marketplace</div>
          </div>
        </Link>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {!user.is_admin && (
                <Link 
                  to="/dashboard" 
                  style={{ 
                    color: COLORS.gray, 
                    textDecoration: 'none', 
                    fontSize: '0.9rem', 
                    fontWeight: '600',
                    padding: '0.5rem 1rem',
                    borderRadius: '8px',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={e => {
                    e.target.style.background = COLORS.lightGray
                    e.target.style.color = COLORS.dark
                  }}
                  onMouseLeave={e => {
                    e.target.style.background = 'transparent'
                    e.target.style.color = COLORS.gray
                  }}
                >
                  📊 My Listings
                </Link>
              )}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.5rem 1rem',
                background: user.is_admin ? '#fef3c7' : '#e0e7ff',
                borderRadius: '20px',
                border: `1px solid ${user.is_admin ? '#fbbf24' : '#c7d2fe'}`
              }}>
                <span style={{ fontSize: '1rem' }}>{user.is_admin ? '👤' : '👤'}</span>
                <span style={{ fontSize: '0.85rem', fontWeight: '600', color: user.is_admin ? '#92400e' : COLORS.primaryDark }}>
                  {user.username}
                </span>
                <span style={{
                  fontSize: '0.65rem',
                  fontWeight: '700',
                  textTransform: 'uppercase',
                  padding: '0.125rem 0.5rem',
                  borderRadius: '10px',
                  background: user.is_admin ? '#fbbf24' : COLORS.primary,
                  color: user.is_admin ? '#92400e' : COLORS.white
                }}>
                  {user.is_admin ? 'Mod' : 'Seller'}
                </span>
              </div>
            </div>
          )}
          {user ? (
            <button
              onClick={handleLogout}
              style={{
                background: 'transparent',
                border: `1.5px solid ${COLORS.gray}`,
                color: COLORS.gray,
                padding: '0.5rem 1.25rem',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '0.9rem',
                fontWeight: '600',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => {
                e.target.style.background = COLORS.danger
                e.target.style.borderColor = COLORS.danger
                e.target.style.color = COLORS.white
              }}
              onMouseLeave={e => {
                e.target.style.background = 'transparent'
                e.target.style.borderColor = COLORS.gray
                e.target.style.color = COLORS.gray
              }}
            >
              Logout
            </button>
          ) : (
            <LoginModal onLogin={handleLogin} />
          )}
        </div>
      </nav>

      {/* Content */}
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
        <Routes>
          <Route path="/" element={<Storefront />} />
          <Route path="/dashboard" element={<UserDashboard user={user} />} />
          <Route path="/submit" element={<SubmitForm user={user} onLogout={handleLogout} />} />
          <Route path="/review" element={<ReviewQueue user={user} />} />
        </Routes>
      </div>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}

export default App
