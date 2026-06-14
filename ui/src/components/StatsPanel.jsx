import { useState, useEffect } from 'react'

const API_BASE = ''

export default function StatsPanel() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/stats`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setStats(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>
  if (error) return <div style={{ padding: '2rem', color: '#e74c3c' }}>Error: {error}</div>
  if (!stats) return null

  const total = stats.total_moderated || 1
  const approvePct = ((stats.auto_approved / total) * 100).toFixed(1)
  const rejectPct = ((stats.auto_rejected / total) * 100).toFixed(1)
  const reviewPct = ((stats.sent_to_review / total) * 100).toFixed(1)

  return (
    <div>
      <h2>Moderation Statistics</h2>
      <button onClick={fetchStats} style={{ marginBottom: '1rem', padding: '0.5rem 1rem' }}>Refresh</button>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.5rem'
      }}>
        <StatCard title="Total Moderated" value={stats.total_moderated} color="#4a90e2" />
        <StatCard title="Auto Approved" value={`${stats.auto_approved} (${approvePct}%)`} color="#27ae60" />
        <StatCard title="Auto Rejected" value={`${stats.auto_rejected} (${rejectPct}%)`} color="#e74c3c" />
        <StatCard title="Sent to Review" value={`${stats.sent_to_review} (${reviewPct}%)`} color="#f39c12" />
        <StatCard title="Queue Depth" value={stats.queue_depth} color="#9b59b6" />
        <StatCard title="Avg Latency" value={`${stats.avg_latency_seconds}s`} color="#34495e" />
      </div>

      <div style={{
        marginTop: '2rem',
        padding: '1.5rem',
        background: 'white',
        borderRadius: '8px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <h3>Thresholds</h3>
        <p><strong>Auto-approve:</strong> {stats.auto_approve_threshold}</p>
        <p><strong>Review threshold:</strong> {stats.review_threshold}</p>
      </div>
    </div>
  )
}

function StatCard({ title, value, color }) {
  return (
    <div style={{
      background: 'white',
      padding: '1.5rem',
      borderRadius: '8px',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      textAlign: 'center'
    }}>
      <div style={{ fontSize: '2rem', fontWeight: 'bold', color }}>{value}</div>
      <div style={{ marginTop: '0.5rem', color: '#666' }}>{title}</div>
    </div>
  )
}
