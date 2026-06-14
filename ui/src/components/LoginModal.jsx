import { useState } from 'react'

const API_BASE = ''
const COLORS = {
  primary: '#6366f1',
  primaryDark: '#4f46e5',
  secondary: '#8b5cf6',
  dark: '#0f172a',
  gray: '#64748b',
  lightGray: '#f1f5f9',
  white: '#ffffff',
  danger: '#ef4444'
}

export default function LoginModal({ onLogin }) {
  const [show, setShow] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)

    try {
      const res = await fetch(`${API_BASE}/api/login`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Invalid username or password')
      onLogin({ id: data.id, username: data.username, is_admin: data.is_admin, is_banned: data.is_banned })
      setShow(false)
      setUsername('')
      setPassword('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!show) {
    return (
      <button
        onClick={() => setShow(true)}
        style={{
          background: `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.secondary} 100%)`,
          border: 'none',
          color: 'white',
          padding: '0.6rem 1.5rem',
          borderRadius: '10px',
          cursor: 'pointer',
          fontSize: '0.95rem',
          fontWeight: '700',
          boxShadow: '0 4px 6px -1px rgba(99, 102, 241, 0.3)',
          transition: 'all 0.2s'
        }}
        onMouseEnter={e => {
          e.target.style.transform = 'translateY(-2px)'
          e.target.style.boxShadow = '0 10px 15px -3px rgba(99, 102, 241, 0.4)'
        }}
        onMouseLeave={e => {
          e.target.style.transform = 'translateY(0)'
          e.target.style.boxShadow = '0 4px 6px -1px rgba(99, 102, 241, 0.3)'
        }}
      >
        🔐 Login
      </button>
    )
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(15, 23, 42, 0.6)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      animation: 'fadeIn 0.2s ease-out'
    }}>
      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
      `}</style>
      
      <div style={{
        background: COLORS.white,
        padding: '2.5rem',
        borderRadius: '16px',
        width: '100%',
        maxWidth: '420px',
        boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
        animation: 'slideUp 0.3s ease-out'
      }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            width: '56px',
            height: '56px',
            background: `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.secondary} 100%)`,
            borderRadius: '14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 1rem',
            fontSize: '1.75rem'
          }}>
            🔐
          </div>
          <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: '800', color: COLORS.dark }}>
            Welcome Back
          </h2>
          <p style={{ margin: '0.5rem 0 0', color: COLORS.gray, fontSize: '0.95rem' }}>
            Login to manage your listings
          </p>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            background: '#fef2f2',
            color: COLORS.danger,
            padding: '0.875rem 1rem',
            borderRadius: '10px',
            marginBottom: '1.5rem',
            fontSize: '0.9rem',
            fontWeight: '600',
            border: '1px solid #fecaca',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem'
          }}>
            <span>⚠️</span> {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Username */}
          <div style={{ marginBottom: '1.5rem' }}>
            <label
              htmlFor="login-username"
              style={{
                display: 'block',
                fontWeight: '700',
                fontSize: '0.95rem',
                marginBottom: '0.5rem',
                color: COLORS.dark
              }}
            >
              Username
            </label>
            <div style={{ position: 'relative' }}>
              <span style={{
                position: 'absolute',
                left: '1rem',
                top: '50%',
                transform: 'translateY(-50%)',
                fontSize: '1.1rem',
                opacity: 0.5
              }}>👤</span>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                placeholder=""
                style={{
                  width: '100%',
                  padding: '0.875rem 1rem 0.875rem 2.75rem',
                  border: '2px solid #e2e8f0',
                  borderRadius: '10px',
                  fontSize: '1rem',
                  transition: 'all 0.2s',
                  outline: 'none'
                }}
                onFocus={e => e.target.style.borderColor = COLORS.primary}
                onBlur={e => e.target.style.borderColor = '#e2e8f0'}
              />
            </div>
          </div>

          {/* Password */}
          <div style={{ marginBottom: '2rem' }}>
            <label
              htmlFor="login-password"
              style={{
                display: 'block',
                fontWeight: '700',
                fontSize: '0.95rem',
                marginBottom: '0.5rem',
                color: COLORS.dark
              }}
            >
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <span style={{
                position: 'absolute',
                left: '1rem',
                top: '50%',
                transform: 'translateY(-50%)',
                fontSize: '1.1rem',
                opacity: 0.5
              }}>🔒</span>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="Enter password"
                style={{
                  width: '100%',
                  padding: '0.875rem 1rem 0.875rem 2.75rem',
                  border: '2px solid #e2e8f0',
                  borderRadius: '10px',
                  fontSize: '1rem',
                  transition: 'all 0.2s',
                  outline: 'none'
                }}
                onFocus={e => e.target.style.borderColor = COLORS.primary}
                onBlur={e => e.target.style.borderColor = '#e2e8f0'}
              />
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '1rem',
              background: loading ? '#cbd5e1' : `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.secondary} 100%)`,
              color: 'white',
              border: 'none',
              borderRadius: '10px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '1rem',
              fontWeight: '700',
              boxShadow: loading ? 'none' : '0 4px 6px -1px rgba(99, 102, 241, 0.3)',
              transition: 'all 0.2s'
            }}
          >
            {loading ? (
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                <span style={{
                  width: '18px',
                  height: '18px',
                  border: '2px solid rgba(255,255,255,0.3)',
                  borderTop: '2px solid white',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite'
                }} />
                Logging in...
              </span>
            ) : 'Login'}
          </button>
        </form>

        {/* Cancel */}
        <button
          onClick={() => { setShow(false); setError(null); }}
          style={{
            marginTop: '1rem',
            width: '100%',
            padding: '0.75rem',
            background: 'transparent',
            color: COLORS.gray,
            border: 'none',
            borderRadius: '10px',
            cursor: 'pointer',
            fontSize: '0.95rem',
            fontWeight: '600',
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
          Cancel
        </button>
      </div>
    </div>
  )
}
