import { useState, useEffect } from 'react'

const API_BASE = ''
const COLORS = {
  primary: '#6366f1',
  success: '#22c55e',
  danger: '#ef4444',
  warning: '#f59e0b',
  dark: '#0f172a',
  gray: '#64748b',
  lightGray: '#f1f5f9',
  white: '#ffffff'
}

export default function UserDashboard({ user }) {
  const [listings, setListings] = useState([])
  const [isBanned, setIsBanned] = useState(false)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState({ title: '', category: '', description: '', price: '' })
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(null)

  useEffect(() => {
    if (user) fetchDashboard()
  }, [user])

  const fetchDashboard = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/my-listings?user_id=${user.username}`)
      if (!res.ok) throw new Error('Failed to load dashboard')
      const data = await res.json()
      setListings(data.listings || [])
      setIsBanned(data.is_banned || false)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = (item) => {
    setEditing(item.id)
    setEditForm({
      title: item.title,
      category: item.category || 'Other',
      description: item.description,
      price: item.price
    })
  }

  const handleSave = async (listingId) => {
    setSaving(true)
    try {
      const formData = new FormData()
      formData.append('user_id', user.username)
      formData.append('title', editForm.title)
      formData.append('category', editForm.category)
      formData.append('description', editForm.description)
      formData.append('price', editForm.price)

      const res = await fetch(`${API_BASE}/api/listings/${listingId}`, {
        method: 'PUT',
        body: formData,
      })
      if (!res.ok) throw new Error('Update failed')
      setEditing(null)
      fetchDashboard()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (listingId) => {
    if (!window.confirm('Are you sure you want to delete this listing? This action cannot be undone.')) {
      return
    }
    setDeleting(listingId)
    try {
      const formData = new FormData()
      formData.append('username', user.username)

      const res = await fetch(`${API_BASE}/api/listings/${listingId}`, {
        method: 'DELETE',
        body: formData,
      })
      if (!res.ok) throw new Error('Delete failed')
      fetchDashboard()
    } catch (err) {
      alert(`Error: ${err.message}`)
    } finally {
      setDeleting(null)
    }
  }

  const getStatusBadge = (status, isPublished) => {
    if (status === 'published' && isPublished) {
      return { text: 'Approved ✅', color: COLORS.success, bg: '#f0fdf4' }
    } else if (status === 'rejected') {
      return { text: 'Rejected ❌', color: COLORS.danger, bg: '#fef2f2' }
    } else {
      return { text: 'Pending ⏳', color: COLORS.warning, bg: '#fffbeb' }
    }
  }

  if (!user) {
    return (
      <div style={{
        textAlign: 'center',
        padding: '5rem 2rem',
        background: COLORS.white,
        borderRadius: '16px',
        boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'
      }}>
        <div style={{ fontSize: '4rem', marginBottom: '1.5rem' }}>👤</div>
        <h2 style={{ color: COLORS.dark, marginBottom: '0.75rem', fontSize: '1.75rem', fontWeight: '800' }}>
          My Listings
        </h2>
        <p style={{ color: COLORS.gray, fontSize: '1.1rem' }}>Please login to view your listings.</p>
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ 
          margin: '0 0 0.5rem 0', 
          fontSize: '1.75rem', 
          fontWeight: '800',
          color: COLORS.dark
        }}>
          My Listings
        </h2>
        <p style={{ color: COLORS.gray, fontSize: '1rem', margin: 0 }}>
          Track your submissions and manage your listings.
        </p>
      </div>

      {/* Banned Banner */}
      {isBanned && (
        <div style={{
          background: '#fef2f2',
          border: '2px solid #fecaca',
          borderRadius: '12px',
          padding: '1.5rem',
          marginBottom: '2rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem'
        }}>
          <span style={{ fontSize: '2rem' }}>🚫</span>
          <div>
            <p style={{ margin: 0, fontWeight: '700', color: COLORS.danger, fontSize: '1.1rem' }}>
              Account Suspended
            </p>
            <p style={{ margin: '0.25rem 0 0', color: '#991b1b', fontSize: '0.9rem' }}>
              Your account has been blocked by a moderator. You cannot submit new listings or edit existing ones.
            </p>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem' }}>Loading...</div>
      ) : listings.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '4rem',
          background: COLORS.white,
          borderRadius: '16px',
          boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'
        }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📭</div>
          <p style={{ color: COLORS.gray, fontSize: '1.1rem' }}>No listings yet. Submit your first item!</p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: '1.5rem'
        }}>
          {listings.map(item => {
            const statusBadge = getStatusBadge(item.status, item.is_published)
            const isEditing = editing === item.id
            const isRejected = item.status === 'rejected'

            return (
              <div key={item.id} style={{
                background: COLORS.white,
                borderRadius: '16px',
                overflow: 'hidden',
                boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
              }}>
                {/* Image */}
                <div style={{
                  height: '200px',
                  background: 'linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)',
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
                    <span style={{ color: '#ccc', fontSize: '3rem' }}>📷</span>
                  )}
                </div>

                <div style={{ padding: '1.25rem' }}>
                  {/* Status Badge */}
                  <div style={{
                    display: 'inline-block',
                    padding: '0.35rem 0.75rem',
                    borderRadius: '20px',
                    fontSize: '0.8rem',
                    fontWeight: '700',
                    background: statusBadge.bg,
                    color: statusBadge.color,
                    marginBottom: '0.75rem'
                  }}>
                    {statusBadge.text}
                  </div>

                  {/* Category Badge */}
                  <div style={{
                    display: 'inline-block',
                    padding: '0.25rem 0.6rem',
                    borderRadius: '6px',
                    fontSize: '0.75rem',
                    fontWeight: '600',
                    background: '#eef2ff',
                    color: COLORS.primary,
                    marginBottom: '0.75rem',
                    marginLeft: '0.5rem'
                  }}>
                    {item.category || 'Other'}
                  </div>

                  {/* Title */}
                  {isEditing ? (
                    <div style={{ marginBottom: '0.75rem' }}>
                      <input
                        type="text"
                        value={editForm.title}
                        onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          border: '2px solid ' + COLORS.primary,
                          borderRadius: '8px',
                          fontSize: '1rem'
                        }}
                      />
                    </div>
                  ) : (
                    <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem', fontWeight: '700', color: COLORS.dark }}>
                      {item.title}
                    </h3>
                  )}

                  {/* Category edit */}
                  {isEditing && (
                    <div style={{ marginBottom: '0.75rem' }}>
                      <select
                        value={editForm.category}
                        onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          border: '2px solid ' + COLORS.primary,
                          borderRadius: '8px',
                          fontSize: '1rem',
                          background: COLORS.white
                        }}
                      >
                        <option value="Electronics">Electronics</option>
                        <option value="Clothing">Clothing</option>
                        <option value="Home">Home & Garden</option>
                        <option value="Vehicles">Vehicles</option>
                        <option value="Services">Services</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>
                  )}

                  {/* Description */}
                  {isEditing ? (
                    <div style={{ marginBottom: '0.75rem' }}>
                      <textarea
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        rows={3}
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          border: '2px solid ' + COLORS.primary,
                          borderRadius: '8px',
                          fontSize: '0.9rem',
                          resize: 'vertical'
                        }}
                      />
                    </div>
                  ) : (
                    <p style={{
                      color: COLORS.gray,
                      fontSize: '0.9rem',
                      lineHeight: '1.4',
                      margin: '0 0 0.75rem 0',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden'
                    }}>
                      {item.description}
                    </p>
                  )}

                  {/* Price */}
                  {isEditing ? (
                    <div style={{ marginBottom: '0.75rem' }}>
                      <input
                        type="number"
                        step="0.01"
                        value={editForm.price}
                        onChange={(e) => setEditForm({ ...editForm, price: e.target.value })}
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          border: '2px solid ' + COLORS.primary,
                          borderRadius: '8px',
                          fontSize: '1rem'
                        }}
                      />
                    </div>
                  ) : (
                    <p style={{ fontSize: '1.25rem', fontWeight: '800', color: COLORS.primary, margin: '0 0 0.75rem' }}>
                      ${item.price.toFixed(2)}
                    </p>
                  )}

                  {/* AI Reasons for rejected */}
                  {isRejected && item.ai_reasons && item.ai_reasons[0] !== 'none' && (
                    <div style={{
                      background: '#fef2f2',
                      padding: '0.75rem',
                      borderRadius: '8px',
                      marginBottom: '0.75rem',
                      fontSize: '0.85rem'
                    }}>
                      <p style={{ margin: 0, color: '#991b1b', fontWeight: '600' }}>
                        ⚠️ {item.ai_reasons?.join(', ') || 'Flagged by moderation'}
                      </p>
                    </div>
                  )}

                  {/* Actions */}
                  {isEditing ? (
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button
                        onClick={() => handleSave(item.id)}
                        disabled={saving}
                        style={{
                          flex: 1,
                          padding: '0.625rem',
                          background: COLORS.primary,
                          color: 'white',
                          border: 'none',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          fontWeight: '700'
                        }}
                      >
                        {saving ? 'Saving...' : '💾 Save'}
                      </button>
                      <button
                        onClick={() => setEditing(null)}
                        style={{
                          flex: 1,
                          padding: '0.625rem',
                          background: COLORS.lightGray,
                          color: COLORS.gray,
                          border: 'none',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          fontWeight: '600'
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {/* Edit & Resubmit - only for rejected listings */}
                      {isRejected && !isBanned && (
                        <button
                          onClick={() => handleEdit(item)}
                          style={{
                            flex: 1,
                            minWidth: '120px',
                            padding: '0.625rem',
                            background: COLORS.warning,
                            color: 'white',
                            border: 'none',
                            borderRadius: '8px',
                            cursor: 'pointer',
                            fontWeight: '700',
                            fontSize: '0.9rem'
                          }}
                        >
                          📝 Edit & Resubmit
                        </button>
                      )}
                      {isRejected && isBanned && (
                        <button
                          disabled
                          style={{
                            flex: 1,
                            minWidth: '120px',
                            padding: '0.625rem',
                            background: '#e5e7eb',
                            color: '#9ca3af',
                            border: 'none',
                            borderRadius: '8px',
                            cursor: 'not-allowed',
                            fontWeight: '600',
                            fontSize: '0.9rem'
                          }}
                        >
                          🔒 Blocked
                        </button>
                      )}
                      {/* Delete - available for all listings */}
                      <button
                        onClick={() => handleDelete(item.id)}
                        disabled={deleting === item.id}
                        style={{
                          flex: 1,
                          minWidth: '80px',
                          padding: '0.625rem',
                          background: COLORS.danger,
                          color: 'white',
                          border: 'none',
                          borderRadius: '8px',
                          cursor: deleting === item.id ? 'not-allowed' : 'pointer',
                          fontWeight: '700',
                          fontSize: '0.9rem',
                          opacity: deleting === item.id ? 0.7 : 1
                        }}
                      >
                        {deleting === item.id ? 'Deleting...' : '🗑️ Delete'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
