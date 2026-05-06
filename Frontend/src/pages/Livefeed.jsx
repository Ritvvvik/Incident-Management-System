// frontend/src/pages/LiveFeed.jsx
import { useState, useEffect, useCallback } from "react";

const INCIDENT_URL = import.meta.env.VITE_INCIDENT_URL || "http://localhost:8001";

const priorityOrder = { P0: 0, P1: 1, P2: 2 };

export default function LiveFeed({ onSelect }) {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchIncidents = useCallback(async () => {
    try {
      const res = await fetch(`${INCIDENT_URL}/incidents`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setIncidents(data.sort((a, b) =>
        priorityOrder[a.priority] - priorityOrder[b.priority]
      ));
      setLastUpdated(new Date());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // auto-refresh every 5 seconds
  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 5000);
    return () => clearInterval(interval);
  }, [fetchIncidents]);

  const badgeClass = (p) => `badge badge-${p.toLowerCase()}`;
  const stateClass = (s) => `state-badge state-${s.toLowerCase()}`;

  const p0 = incidents.filter(i => i.priority === "P0");
  const p1 = incidents.filter(i => i.priority === "P1");
  const p2 = incidents.filter(i => i.priority === "P2");

  if (loading) return (
    <div className="loading">
      <div className="spinner" /> Fetching incidents...
    </div>
  );

  return (
    <div>
      {/* ── Top bar ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontFamily: "var(--sans)", fontSize: 24, fontWeight: 800 }}>
            Live Incident Feed
          </h1>
          <p style={{ color: "var(--text2)", fontSize: 12, marginTop: 4 }}>
            Auto-refreshes every 5s
            {lastUpdated && ` · Last updated ${lastUpdated.toLocaleTimeString()}`}
          </p>
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <StatPill label="P0 Critical" count={p0.length} color="var(--p0)" />
          <StatPill label="P1 High"     count={p1.length} color="var(--p1)" />
          <StatPill label="P2 Medium"   count={p2.length} color="var(--p2)" />
        </div>
      </div>

      {error && <div className="error-box" style={{ marginBottom: 16 }}>⚠ {error}</div>}

      {incidents.length === 0 && !error && (
        <div className="empty">
          <div style={{ fontSize: 32, marginBottom: 12 }}>✓</div>
          No active incidents. System healthy.
        </div>
      )}

      {/* ── Incident rows ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {incidents.map((inc, i) => (
          <div
            key={inc.id}
            className="card"
            onClick={() => onSelect(inc)}
            style={{
              cursor: "pointer",
              borderLeft: `3px solid ${inc.priority === "P0" ? "var(--p0)" : inc.priority === "P1" ? "var(--p1)" : "var(--p2)"}`,
              transition: "all .15s",
              animation: `fadeIn .3s ease ${i * 0.04}s both`,
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = "var(--blue)"}
            onMouseLeave={e => e.currentTarget.style.borderColor = inc.priority === "P0" ? "var(--p0)" : inc.priority === "P1" ? "var(--p1)" : "var(--p2)"}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className={badgeClass(inc.priority)}>{inc.priority}</span>
              <span style={{ flex: 1, fontWeight: 500 }}>{inc.component_id}</span>
              <span className={stateClass(inc.state)}>{inc.state}</span>
              <span style={{ color: "var(--text2)", fontSize: 12 }}>
                {new Date(inc.start_time).toLocaleString()}
              </span>
              <span style={{ color: "var(--text3)", fontSize: 12 }}>›</span>
            </div>
            <div style={{ marginTop: 8, display: "flex", gap: 16 }}>
              <Meta label="Type"       value={inc.component_type} />
              <Meta label="ID"         value={inc.id?.slice(0, 8) + "..."} />
              {inc.mttr_seconds && (
                <Meta label="MTTR" value={`${Math.round(inc.mttr_seconds / 60)}m`} />
              )}
            </div>
          </div>
        ))}
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
      `}</style>
    </div>
  );
}

function StatPill({ label, count, color }) {
  return (
    <div style={{
      background: "var(--bg3)", border: `1px solid ${color}`,
      borderRadius: 8, padding: "8px 14px", textAlign: "center"
    }}>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{count}</div>
      <div style={{ fontSize: 11, color: "var(--text2)" }}>{label}</div>
    </div>
  );
}

function Meta({ label, value }) {
  return (
    <span style={{ fontSize: 12, color: "var(--text2)" }}>
      <span style={{ color: "var(--text3)" }}>{label}: </span>{value}
    </span>
  );
}