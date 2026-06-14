import { useState, useEffect } from 'react'

const API_BASE = ''

export default function ReviewQueue({ user }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState({})

  const fetchQueue = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/review-queue`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setItems(data.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchQueue()
    const interval = setInterval(fetchQueue, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleAction = async (listingId, action) => {
    setActionLoading(prev => ({ ...prev, [listingId]: true }))
    try {
      const formData = new FormData()
      formData.append('action', action)
      formData.append('moderator', user?.username || 'admin')

      const res = await fetch(`${API_BASE}/api/review/${listingId}`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`HTTP ${res.status}: ${text}`)
      }
      await fetchQueue()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(prev => ({ ...prev, [listingId]: false }))
    }
  }

  const handleBlockUser = async (username) => {
    if (!confirm(`Are you sure you want to BLOCK user "${username}"? They will no longer be able to submit listings.`)) {
      return
    }
    try {
      const formData = new FormData()
      formData.append('moderator', user?.username || 'admin')

      const res = await fetch(`${API_BASE}/api/ban-user/${username}`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`HTTP ${res.status}: ${text}`)
      }
      alert(`User "${username}" has been blocked.`)
      await fetchQueue()
    } catch (err) {
      alert(`Error: ${err.message}`)
    }
  }

  const handleDelete = async (listingId, title) => {
    if (!confirm(`Delete listing "${title}" permanently? This cannot be undone.`)) {
      return
    }
    setActionLoading(prev => ({ ...prev, [listingId]: true }))
    try {
      const formData = new FormData()
      formData.append('username', user?.username || 'admin')

      const res = await fetch(`${API_BASE}/api/listings/${listingId}`, {
        method: 'DELETE',
        body: formData,
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`HTTP ${res.status}: ${text}`)
      }
      await fetchQueue()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setActionLoading(prev => ({ ...prev, [listingId]: false }))
    }
  }

  if (!user?.is_admin) {
    return (
      <div style={{
        textAlign: 'center',
        padding: '4rem 2rem',
        background: 'white',
        borderRadius: '12px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
      }}>
        <h2>Access Denied</h2>
        <p style={{ color: '#666' }}>This area is for moderators only.</p>
      </div>
    )
  }

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>
  if (error) return <div style={{ padding: '2rem', color: '#e74c3c' }}>Error: {error}</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>Moderation Queue ({items.length} pending)</h2>
        <button onClick={fetchQueue} style={{ padding: '0.5rem 1rem', background: '#667eea', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          Refresh
        </button>
      </div>

      {items.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '3rem',
          background: 'white',
          borderRadius: '12px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
        }}>
          <p style={{ color: '#27ae60', fontSize: '1.2rem' }}>No items in review queue. All caught up!</p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: '1.5rem'
        }}>
          {items.map(item => (
            <div
              key={item.id}
              style={{
                background: 'white',
                borderRadius: '12px',
                overflow: 'hidden',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                transition: 'transform 0.2s, box-shadow 0.2s',
                cursor: 'default'
              }}
            >
              {/* Image */}
              <div style={{
                height: '200px',
                background: '#f0f0f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden'
              }}>
                {item.image_url ? (
                  <img
                    src={item.image_url}
                    alt={item.title}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <span style={{ color: '#ccc', fontSize: '3rem' }}>No Image</span>
                )}
              </div>

              {/* Content — same layout as Storefront */}
              <div style={{ padding: '1.25rem' }}>
                {/* Title */}
                <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem', color: '#333' }}>
                  {item.title}
                </h3>

                {/* Category + Submitter */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{
                    display: 'inline-block',
                    padding: '0.2rem 0.6rem',
                    borderRadius: '6px',
                    fontSize: '0.75rem',
                    fontWeight: '600',
                    background: '#eef2ff',
                    color: '#667eea'
                  }}>
                    {item.category || 'Other'}
                  </span>
                  <span style={{
                    fontSize: '0.8rem',
                    color: '#999',
                    fontWeight: '500'
                  }}>
                    by {item.submitter || 'unknown'}
                  </span>
                </div>

                {/* Description — same style as Storefront */}
                <p style={{
                  color: '#666',
                  fontSize: '0.9rem',
                  lineHeight: '1.4',
                  margin: '0 0 1rem 0',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden'
                }}>
                  {item.description}
                </p>

                {/* Price */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <span style={{
                    fontSize: '1.25rem',
                    fontWeight: 'bold',
                    color: '#667eea'
                  }}>
                    ${item.price}
                  </span>
                  <span style={{
                    display: 'inline-block',
                    padding: '0.25rem 0.75rem',
                    borderRadius: '20px',
                    fontSize: '0.75rem',
                    fontWeight: 'bold',
                    textTransform: 'uppercase',
                    background: item.priority === 'high' ? '#ffebee' : item.priority === 'low' ? '#e8f5e9' : '#fff3e0',
                    color: item.priority === 'high' ? '#c62828' : item.priority === 'low' ? '#2e7d32' : '#ef6c00'
                  }}>
                    {item.priority} Priority
                  </span>
                </div>

                {/* AI Info — compact */}
                <div style={{
                  background: '#f8f9fa',
                  padding: '0.75rem',
                  borderRadius: '8px',
                  marginBottom: '1rem',
                  fontSize: '0.85rem'
                }}>
                  <p style={{ margin: '0 0 0.25rem 0', fontWeight: '500' }}>
                    AI: <span style={{
                      color: item.ai_decision === 'APPROVE' ? '#27ae60' : item.ai_decision === 'REJECT' ? '#e74c3c' : '#f39c12',
                      fontWeight: 'bold'
                    }}>{item.ai_decision}</span>
                    <span style={{ color: '#666' }}> ({(item.ai_confidence * 100).toFixed(0)}%)</span>
                  </p>
                  <p style={{ margin: '0', color: '#666', fontSize: '0.8rem' }}>
                    {item.ai_reasons?.join(', ') || 'No issues flagged'}
                  </p>
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem' }}>
                  <button
                    onClick={() => handleAction(item.listing_id, 'publish')}
                    disabled={actionLoading[item.listing_id]}
                    style={{
                      flex: 1,
                      padding: '0.75rem',
                      background: '#27ae60',
                      color: 'white',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontSize: '0.95rem',
                      fontWeight: '700'
                    }}
                  >
                    ✅ Publish
                  </button>
                  <button
                    onClick={() => handleAction(item.listing_id, 'ban')}
                    disabled={actionLoading[item.listing_id]}
                    style={{
                      flex: 1,
                      padding: '0.75rem',
                      background: '#e74c3c',
                      color: 'white',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontSize: '0.95rem',
                      fontWeight: '700'
                    }}
                  >
                    ❌ Ban
                  </button>
                </div>

                {/* Delete + Block User */}
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => handleDelete(item.listing_id, item.title)}
                    disabled={actionLoading[item.listing_id]}
                    style={{
                      flex: 1,
                      padding: '0.625rem',
                      background: '#fee2e2',
                      color: '#dc2626',
                      border: '2px solid #fca5a5',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                      fontWeight: '700',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={e => {
                      e.target.style.background = '#fca5a5'
                      e.target.style.color = '#991b1b'
                    }}
                    onMouseLeave={e => {
                      e.target.style.background = '#fee2e2'
                      e.target.style.color = '#dc2626'
                    }}
                  >
                    🗑️ Delete
                  </button>
                  <button
                    onClick={() => handleBlockUser(item.submitter)}
                    style={{
                      flex: 1,
                      padding: '0.625rem',
                      background: '#fef3c7',
                      color: '#92400e',
                      border: '2px solid #fbbf24',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                      fontWeight: '700',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={e => {
                      e.target.style.background = '#fbbf24'
                      e.target.style.color = '#78350f'
                    }}
                    onMouseLeave={e => {
                      e.target.style.background = '#fef3c7'
                      e.target.style.color = '#92400e'
                    }}
                  >
                    🚫 Block User
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
