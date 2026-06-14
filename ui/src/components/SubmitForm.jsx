import { useState } from 'react'

const API_BASE = ''
const COLORS = {
  primary: '#6366f1',
  primaryDark: '#4f46e5',
  secondary: '#8b5cf6',
  success: '#22c55e',
  danger: '#ef4444',
  dark: '#0f172a',
  gray: '#64748b',
  lightGray: '#f1f5f9',
  white: '#ffffff'
}

export default function SubmitForm({ user, onLogout }) {
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [price, setPrice] = useState('')
  const [images, setImages] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png']
  const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png']

  const filterFiles = (fileList) => {
    const valid = []
    const rejected = []
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'))
      const isAllowedType = ALLOWED_MIME_TYPES.includes(file.type)
      const isAllowedExt = ALLOWED_EXTENSIONS.includes(ext)
      if (isAllowedType || isAllowedExt) {
        valid.push(file)
      } else {
        rejected.push(file.name)
      }
    }
    return { valid, rejected }
  }

  const handleFiles = (fileList) => {
    if (!fileList || fileList.length === 0) return
    const { valid, rejected } = filterFiles(fileList)
    if (valid.length > 0) {
      const dt = new DataTransfer()
      valid.forEach(f => dt.items.add(f))
      setImages(dt.files)
    }
    if (rejected.length > 0) {
      setResult({
        error: `Rejected ${rejected.length} file(s): ${rejected.join(', ')}. Only JPG, JPEG, and PNG allowed.`
      })
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!images || images.length === 0) {
      setResult({ error: 'Please select at least one image (JPG, JPEG, or PNG)' })
      return
    }
    const { valid, rejected } = filterFiles(images)
    if (valid.length === 0) {
      setResult({ error: `No valid images. Rejected: ${rejected.join(', ')}. Only JPG, JPEG, and PNG allowed.` })
      return
    }
    setLoading(true)
    setResult(null)

    const formData = new FormData()
    formData.append('user_id', user?.username || '')
    formData.append('title', title)
    formData.append('category', category)
    formData.append('description', description)
    formData.append('price', price)
    for (let i = 0; i < valid.length; i++) {
      formData.append('images', valid[i])
    }

    try {
      const res = await fetch(`${API_BASE}/api/submit`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Submission failed')
      setResult({ success: true, ...data })
    } catch (err) {
      setResult({ error: err.message })
    } finally {
      setLoading(false)
    }
  }

  const resetForm = () => {
    setTitle('')
    setCategory('')
    setDescription('')
    setPrice('')
    setImages(null)
    setResult(null)
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
        <div style={{ fontSize: '4rem', marginBottom: '1.5rem' }}>🏪</div>
        <h2 style={{ color: COLORS.dark, marginBottom: '0.75rem', fontSize: '1.75rem', fontWeight: '800' }}>
          Want to sell something?
        </h2>
        <p style={{ color: COLORS.gray, fontSize: '1.1rem', maxWidth: '400px', margin: '0 auto', lineHeight: '1.6' }}>
          Login to submit your listing and reach buyers in our community.
        </p>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: '640px', margin: '0 auto' }}>
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ 
          margin: '0 0 0.5rem 0', 
          fontSize: '1.75rem', 
          fontWeight: '800',
          color: COLORS.dark
        }}>
          Create Listing
        </h2>
        <p style={{ color: COLORS.gray, fontSize: '1rem', margin: 0 }}>
          Fill in the details below to list your item for sale.
        </p>
      </div>

      {result?.success ? (
        <div style={{
          background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
          padding: '2.5rem',
          borderRadius: '16px',
          textAlign: 'center',
          border: '2px solid #86efac',
          animation: 'slideUp 0.4s ease-out'
        }}>
          <style>{`@keyframes slideUp { from { transform: translateY(10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }`}</style>
          
          <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>✅</div>
          <h3 style={{ color: '#15803d', marginBottom: '0.75rem', fontSize: '1.5rem', fontWeight: '800' }}>
            Listing Submitted!
          </h3>
          <p style={{ color: '#166534', marginBottom: '1.5rem', fontSize: '1.05rem' }}>
            {result.message || "It will appear in the store once approved."}
          </p>
          <p style={{ color: COLORS.gray, fontSize: '0.9rem', marginBottom: '2rem' }}>
            Status: <span style={{ fontWeight: '700', color: COLORS.primary }}>{result.status === 'pending_review' ? 'Under review' : result.status}</span>
          </p>
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
            <button
              onClick={resetForm}
              style={{
                padding: '0.875rem 1.75rem',
                background: `linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.secondary} 100%)`,
                color: 'white',
                border: 'none',
                borderRadius: '10px',
                cursor: 'pointer',
                fontSize: '1rem',
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
              📝 Submit Another
            </button>
            <button
              onClick={onLogout}
              style={{
                padding: '0.875rem 1.75rem',
                background: COLORS.white,
                color: COLORS.gray,
                border: '2px solid #e2e8f0',
                borderRadius: '10px',
                cursor: 'pointer',
                fontSize: '1rem',
                fontWeight: '600',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => {
                e.target.style.borderColor = COLORS.danger
                e.target.style.color = COLORS.danger
              }}
              onMouseLeave={e => {
                e.target.style.borderColor = '#e2e8f0'
                e.target.style.color = COLORS.gray
              }}
            >
              🚪 Logout
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ 
          background: COLORS.white, 
          padding: '2.5rem', 
          borderRadius: '16px', 
          boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)'
        }}>
          {result?.error && (
            <div style={{
              background: '#fef2f2',
              color: COLORS.danger,
              padding: '1rem',
              borderRadius: '10px',
              marginBottom: '1.5rem',
              border: '1px solid #fecaca',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}>
              <span>⚠️</span> {result.error}
            </div>
          )}

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ 
              display: 'block', 
              fontWeight: '700', 
              fontSize: '0.95rem', 
              marginBottom: '0.5rem',
              color: COLORS.dark
            }}>
              📝 Title
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder="What are you selling?"
              style={{ 
                width: '100%', 
                padding: '0.875rem 1rem', 
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

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{
              display: 'block',
              fontWeight: '700',
              fontSize: '0.95rem',
              marginBottom: '0.5rem',
              color: COLORS.dark
            }}>
              🏷️ Category
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.875rem 1rem',
                border: '2px solid #e2e8f0',
                borderRadius: '10px',
                fontSize: '1rem',
                transition: 'all 0.2s',
                outline: 'none',
                background: COLORS.white,
                cursor: 'pointer'
              }}
              onFocus={e => e.target.style.borderColor = COLORS.primary}
              onBlur={e => e.target.style.borderColor = '#e2e8f0'}
            >
              <option value="">Select a category...</option>
              <option value="Electronics">Electronics</option>
              <option value="Clothing">Clothing</option>
              <option value="Home">Home & Garden</option>
              <option value="Vehicles">Vehicles</option>
              <option value="Services">Services</option>
              <option value="Other">Other</option>
            </select>
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ 
              display: 'block', 
              fontWeight: '700', 
              fontSize: '0.95rem', 
              marginBottom: '0.5rem',
              color: COLORS.dark
            }}>
              📄 Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              rows={5}
              placeholder="Describe your item in detail..."
              style={{ 
                width: '100%', 
                padding: '0.875rem 1rem', 
                border: '2px solid #e2e8f0', 
                borderRadius: '10px',
                fontSize: '1rem',
                transition: 'all 0.2s',
                outline: 'none',
                resize: 'vertical'
              }}
              onFocus={e => e.target.style.borderColor = COLORS.primary}
              onBlur={e => e.target.style.borderColor = '#e2e8f0'}
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ 
              display: 'block', 
              fontWeight: '700', 
              fontSize: '0.95rem', 
              marginBottom: '0.5rem',
              color: COLORS.dark
            }}>
              💰 Price ($)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              required
              placeholder="0.00"
              style={{ 
                width: '100%', 
                padding: '0.875rem 1rem', 
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

          <div style={{ marginBottom: '2rem' }}>
            <label style={{ 
              display: 'block', 
              fontWeight: '700', 
              fontSize: '0.95rem', 
              marginBottom: '0.5rem',
              color: COLORS.dark
            }}>
              📸 Images
            </label>
            <div
              onClick={() => document.getElementById('file-upload')?.click()}
              onDragOver={e => {
                e.preventDefault()
                e.stopPropagation()
                e.currentTarget.style.borderColor = COLORS.primary
                e.currentTarget.style.background = '#eef2ff'
              }}
              onDragLeave={e => {
                e.preventDefault()
                e.stopPropagation()
                e.currentTarget.style.borderColor = '#cbd5e1'
                e.currentTarget.style.background = 'transparent'
              }}
              onDrop={e => {
                e.preventDefault()
                e.stopPropagation()
                e.currentTarget.style.borderColor = '#cbd5e1'
                e.currentTarget.style.background = 'transparent'
                handleFiles(e.dataTransfer.files)
              }}
              style={{
                border: '2px dashed #cbd5e1',
                borderRadius: '12px',
                padding: '2rem',
                textAlign: 'center',
                transition: 'all 0.2s',
                cursor: 'pointer'
              }}
            >
              <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>📤</div>
              <p style={{ color: COLORS.gray, marginBottom: '1rem', fontSize: '0.95rem' }}>
                Drag & drop JPG, JPEG, or PNG images here or click to browse
              </p>
              <input
                type="file"
                accept=".jpg,.jpeg,.png"
                multiple
                onChange={(e) => {
                  handleFiles(e.target.files)
                }}
                style={{ display: 'none' }}
                id="file-upload"
              />
              <span style={{
                display: 'inline-block',
                padding: '0.625rem 1.25rem',
                background: COLORS.lightGray,
                color: COLORS.dark,
                borderRadius: '8px',
                fontSize: '0.9rem',
                fontWeight: '600',
                transition: 'all 0.2s',
                pointerEvents: 'none'
              }}>
                Choose Files
              </span>
            </div>
            {images && images.length > 0 && (
              <p style={{ color: COLORS.success, fontSize: '0.9rem', marginTop: '0.75rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span>✅</span> {images.length} image(s) selected
              </p>
            )}
          </div>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'space-between' }}>
            <button
              type="submit"
              disabled={loading}
              style={{
                flex: 1,
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
                  Submitting...
                </span>
              ) : '🚀 Submit Listing'}
            </button>

            <button
              type="button"
              onClick={onLogout}
              style={{
                padding: '1rem 1.75rem',
                background: COLORS.white,
                color: COLORS.gray,
                border: '2px solid #e2e8f0',
                borderRadius: '10px',
                cursor: 'pointer',
                fontSize: '1rem',
                fontWeight: '600',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => {
                e.target.style.borderColor = COLORS.danger
                e.target.style.color = COLORS.danger
              }}
              onMouseLeave={e => {
                e.target.style.borderColor = '#e2e8f0'
                e.target.style.color = COLORS.gray
              }}
            >
              🚪 Logout
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
