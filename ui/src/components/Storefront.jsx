import { useState, useEffect } from 'react'

const API_BASE = ''
const COLORS = {
  primary: '#6366f1',
  primaryDark: '#4f46e5',
  secondary: '#8b5cf6',
  accent: '#06b6d4',
  success: '#22c55e',
  danger: '#ef4444',
  dark: '#0f172a',
  gray: '#64748b',
  lightGray: '#f1f5f9',
  white: '#ffffff'
}

export default function Storefront() {
  const [listings, setListings] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchListings()
  }, [])

  const fetchListings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/listings`)
      if (!res.ok) throw new Error('Failed to load listings')
      const data = await res.json()
      setListings(data.listings || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      {/* Hero Banner - Animated CSS Scene */}
      <div style={{
        position: 'relative',
        overflow: 'hidden',
        background: 'linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4c1d95 100%)',
        color: 'white',
        padding: '4rem 2rem',
        borderRadius: '16px',
        marginBottom: '2.5rem',
        boxShadow: '0 25px 50px -12px rgba(76, 29, 149, 0.4)',
        minHeight: '280px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        textAlign: 'center'
      }}>
        {/* Animated floating elements */}
        <style>{`
          @keyframes float {
            0%, 100% { transform: translateY(0px) rotate(0deg); }
            50% { transform: translateY(-20px) rotate(5deg); }
          }
          @keyframes float-delayed {
            0%, 100% { transform: translateY(0px) rotate(0deg); }
            50% { transform: translateY(-15px) rotate(-5deg); }
          }
          @keyframes pulse {
            0%, 100% { opacity: 0.6; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.2); }
          }
          @keyframes slide-bg {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
          }
        `}</style>
        
        {/* Floating shopping bag */}
        <div style={{
          position: 'absolute',
          top: '15%',
          left: '10%',
          fontSize: '3rem',
          animation: 'float 4s ease-in-out infinite',
          opacity: 0.8
        }}>🛍️</div>
        
        {/* Floating cart */}
        <div style={{
          position: 'absolute',
          top: '20%',
          right: '12%',
          fontSize: '2.5rem',
          animation: 'float-delayed 5s ease-in-out infinite',
          opacity: 0.7
        }}>🛒</div>
        
        {/* Floating coins */}
        <div style={{
          position: 'absolute',
          bottom: '20%',
          left: '15%',
          fontSize: '2rem',
          animation: 'pulse 3s ease-in-out infinite',
          opacity: 0.6
        }}>💰</div>
        
        <div style={{
          position: 'absolute',
          bottom: '25%',
          right: '18%',
          fontSize: '1.8rem',
          animation: 'pulse 3.5s ease-in-out infinite 0.5s',
          opacity: 0.6
        }}>💎</div>
        
        {/* Floating stars */}
        <div style={{
          position: 'absolute',
          top: '40%',
          left: '5%',
          fontSize: '1.2rem',
          animation: 'pulse 2s ease-in-out infinite',
          opacity: 0.5
        }}>✨</div>
        
        <div style={{
          position: 'absolute',
          top: '35%',
          right: '8%',
          fontSize: '1.5rem',
          animation: 'pulse 2.5s ease-in-out infinite 1s',
          opacity: 0.5
        }}>⭐</div>
        
        {/* Main content */}
        <div style={{ position: 'relative', zIndex: 2 }}>
          <h1 style={{ 
            fontSize: '3.5rem', 
            marginBottom: '0.75rem',
            fontWeight: '900',
            letterSpacing: '-0.02em',
            textShadow: '0 4px 20px rgba(0,0,0,0.3)'
          }}>
            Cashi Shop
          </h1>
          <p style={{ 
            fontSize: '1.35rem', 
            opacity: 0.95,
            fontWeight: '400',
            maxWidth: '600px',
            margin: '0 auto',
            lineHeight: '1.5'
          }}>
            Buy & Sell
          </p>
        </div>
      </div>

      {/* Listings Grid */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '4rem' }}>
          <div style={{
            width: '48px',
            height: '48px',
            border: `4px solid ${COLORS.lightGray}`,
            borderTop: `4px solid ${COLORS.primary}`,
            borderRadius: '50%',
            margin: '0 auto 1rem',
            animation: 'spin 1s linear infinite'
          }} />
          <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
          <p style={{ color: COLORS.gray, fontSize: '1rem' }}>Loading listings...</p>
        </div>
      ) : listings.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '5rem 2rem',
          background: COLORS.white,
          borderRadius: '16px',
          boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)'
        }}>
          <div style={{ fontSize: '4rem', marginBottom: '1.5rem' }}>🏪</div>
          <h2 style={{ color: COLORS.dark, marginBottom: '0.75rem', fontSize: '1.5rem', fontWeight: '700' }}>
            No listings yet
          </h2>
          <p style={{ color: COLORS.gray, fontSize: '1.1rem', maxWidth: '400px', margin: '0 auto 1.5rem', lineHeight: '1.6' }}>
            Be the first to sell something awesome! Login as a seller to get started.
          </p>
        </div>
      ) : (
        <div>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '1.5rem'
          }}>
            <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: '700', color: COLORS.dark }}>
              Latest Listings
            </h2>
            <span style={{ color: COLORS.gray, fontSize: '0.9rem', fontWeight: '500' }}>
              {listings.length} {listings.length === 1 ? 'item' : 'items'}
            </span>
          </div>
          
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '2rem'
          }}>
            {listings.map((item, index) => (
              <div key={item.id} style={{
                background: COLORS.white,
                borderRadius: '16px',
                overflow: 'hidden',
                boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                cursor: 'pointer',
                position: 'relative'
              }} onMouseEnter={e => {
                e.currentTarget.style.transform = 'translateY(-8px)'
                e.currentTarget.style.boxShadow = '0 25px 50px -12px rgba(0,0,0,0.25)'
              }} onMouseLeave={e => {
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)'
              }}>
                {/* NEW Badge */}
                {index < 3 && (
                  <div style={{
                    position: 'absolute',
                    top: '12px',
                    left: '12px',
                    background: COLORS.accent,
                    color: 'white',
                    padding: '0.35rem 0.85rem',
                    borderRadius: '20px',
                    fontSize: '0.75rem',
                    fontWeight: '700',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    zIndex: 10,
                    boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
                  }}>
                    NEW
                  </div>
                )}

                {/* Image */}
                <div style={{
                  height: '240px',
                  background: 'linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                  position: 'relative'
                }}>
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt={item.title}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'transform 0.3s' }}
                      onMouseEnter={e => e.target.style.transform = 'scale(1.05)'}
                      onMouseLeave={e => e.target.style.transform = 'scale(1)'}
                    />
                  ) : (
                    <div style={{ textAlign: 'center' }}>
                      <span style={{ fontSize: '3rem' }}>📷</span>
                      <p style={{ color: COLORS.gray, fontSize: '0.9rem', marginTop: '0.5rem' }}>No Image</p>
                    </div>
                  )}
                </div>

                {/* Content */}
                <div style={{ padding: '1.5rem' }}>
                  <h3 style={{ 
                    margin: '0 0 0.5rem 0', 
                    fontSize: '1.2rem', 
                    fontWeight: '700',
                    color: COLORS.dark,
                    lineHeight: '1.3'
                  }}>
                    {item.title}
                  </h3>
                  <div style={{ marginBottom: '0.75rem' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '0.25rem 0.6rem',
                      borderRadius: '6px',
                      fontSize: '0.75rem',
                      fontWeight: '600',
                      background: '#eef2ff',
                      color: COLORS.primary
                    }}>
                      {item.category || 'Other'}
                    </span>
                  </div>
                  <p style={{
                    color: COLORS.gray,
                    fontSize: '0.95rem',
                    lineHeight: '1.5',
                    margin: '0 0 1.25rem 0',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden'
                  }}>
                    {item.description}
                  </p>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}>
                    <div>
                      <span style={{
                        fontSize: '1.5rem',
                        fontWeight: '800',
                        color: COLORS.primary,
                        letterSpacing: '-0.02em'
                      }}>
                        ${item.price.toFixed(2)}
                      </span>
                    </div>
                    <span style={{ 
                      color: COLORS.gray, 
                      fontSize: '0.85rem',
                      fontWeight: '500'
                    }}>
                      {new Date(item.created_at).toLocaleDateString('en-US', { 
                        month: 'short', 
                        day: 'numeric' 
                      })}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
