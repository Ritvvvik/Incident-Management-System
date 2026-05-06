// frontend/src/pages/IncidentDetail.jsx
import { useState, useEffect } from "react";

const INCIDENT_URL = import.meta.env.VITE_INCIDENT_URL || "http://localhost:8001";

const NEXT_STATE = {
  OPEN:          "INVESTIGATING",
  INVESTIGATING: "RESOLVED",
  RESOLVED:      "CLOSED",
  CLOSED:        null,
};

export default function IncidentDetail({ incident, onBack, onRCA }) {
  const [detail, setDetail]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [transitioning, setTransitioning] = useState(false);

  useEffect(() => {
    fetchDetail();
  }, [incident.id]);

  async function fetchDetail() {
    setLoading(true);
    try {
      const res = await fetch(`${INCIDENT_URL}/incidents/${incident.id}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDetail(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleTransition() {
    const inc = detail?.incident;
    const nextState = NEXT_STATE[inc?.state];
    if (!nextState) return;

    // RCA required before CLOSED
    if (nextState === "CLOSED") {
      onRCA(inc);
      return;
    }

    setTransitioning(true);
    try {
      const res = await fetch(`${INCIDENT_URL}/incidents/${inc.id}/state`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_state: nextState }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Transition failed");
      }
      await fetchDetail();
    } catch (e) {
      setError(e.message);
    } finally {
      setTransitioning(false);
    }
  }

  if (loading) return <div className="loading"><div className="spinner" /> Loading incident...</div>;
  if (error)   return <div className="error-box">⚠ {error}</div>;

  const inc     = detail?.incident;
  const signals = detail?.signals || [];
  const nextState = NEXT_STATE[inc?.state];
  const priorityColor = inc?.priority === "P0" ? "var(--p0)" : inc?.priority === "P1" ? "var(--p1)" : "var(--p2)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* ── Back + title ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        <h1 style={{ fontFamily: "var(--sans)", fontSize: 22, fontWeight: 800, flex: 1 }}>
          {inc?.component_id}
        </h1>
        <span className={`badge badge-${inc?.priority?.toLowerCase()}`}>{inc?.priority}</span>
        <span className={`state-badge state-${inc?.state?.toLowerCase()}`}>{inc?.state}</span>
      </div>

      {/* ── Incident metadata ── */}
      <div className="card" style={{ borderTop: `3px solid ${priorityColor}` }}>
        <h2 style={{ fontFamily: "var(--sans)", fontSize: 15, fontWeight: 700, marginBottom: 16 }}>
          Incident Details
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          <DetailRow label="Incident ID"     value={inc?.id} mono />
          <DetailRow label="Component Type"  value={inc?.component_type} />
          <DetailRow label="Priority"        value={inc?.priority} />
          <DetailRow label="State"           value={inc?.state} />
          <DetailRow label="Start Time"      value={new Date(inc?.start_time).toLocaleString()} />
          <DetailRow label="MTTR"            value={inc?.mttr_seconds ? `${Math.round(inc.mttr_seconds / 60)} minutes` : "—"} />
        </div>

        {/* State transition */}
        {nextState && (
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ color: "var(--text2)", fontSize: 13 }}>
              Transition to:
            </span>
            <button
              className={nextState === "CLOSED" ? "btn btn-danger" : "btn btn-primary"}
              onClick={handleTransition}
              disabled={transitioning}
            >
              {transitioning ? "..." : nextState === "CLOSED" ? "Submit RCA & Close" : `→ ${nextState}`}
            </button>
            {nextState === "CLOSED" && (
              <span style={{ fontSize: 12, color: "var(--text2)" }}>
                RCA required before closing
              </span>
            )}
          </div>
        )}

        {inc?.state === "CLOSED" && (
          <div style={{ marginTop: 16, color: "var(--p2)", fontSize: 13 }}>
            ✓ Incident closed. MTTR: {Math.round(inc.mttr_seconds / 60)} minutes.
          </div>
        )}
      </div>

      {/* ── Raw signals ── */}
      <div className="card">
        <h2 style={{ fontFamily: "var(--sans)", fontSize: 15, fontWeight: 700, marginBottom: 16 }}>
          Raw Signals ({signals.length})
        </h2>

        {signals.length === 0 && (
          <div style={{ color: "var(--text2)", fontSize: 13 }}>No signals found.</div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 400, overflowY: "auto" }}>
          {signals.map((sig, i) => (
            <div key={i} style={{
              background: "var(--bg3)", border: "1px solid var(--border)",
              borderRadius: 6, padding: "10px 14px",
              fontSize: 12, fontFamily: "var(--mono)"
            }}>
              <div style={{ display: "flex", gap: 16, marginBottom: 6 }}>
                <span style={{ color: "var(--p0)" }}>{sig.error_type}</span>
                <span style={{ color: "var(--text2)" }}>{new Date(sig.timestamp).toLocaleTimeString()}</span>
                <span style={{ color: "var(--text3)" }}>id: {sig.signal_id?.slice(0, 8)}</span>
              </div>
              <pre style={{ color: "var(--text2)", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                {JSON.stringify(sig.payload, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value, mono }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4, letterSpacing: ".05em" }}>{label}</div>
      <div style={{ fontSize: 13, color: "var(--text)", fontFamily: mono ? "var(--mono)" : "inherit", wordBreak: "break-all" }}>
        {value || "—"}
      </div>
    </div>
  );
}