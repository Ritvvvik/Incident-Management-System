// frontend/src/pages/RCAForm.jsx
import { useState } from "react";

const INCIDENT_URL = import.meta.env.VITE_INCIDENT_URL || "http://localhost:8001";

const CATEGORIES = [
  "Infrastructure",
  "Code Bug",
  "Human Error",
  "Third Party",
  "Capacity",
  "Security",
  "Unknown",
];

export default function RCAForm({ incident, onBack, onSuccess }) {
  const [form, setForm] = useState({
    root_cause_category: "",
    problem_description: "",
    fix_applied:         "",
    prevention_steps:    "",
    incident_start:      incident?.start_time?.slice(0, 16) || "",
    incident_end:        "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError]           = useState(null);
  const [success, setSuccess]       = useState(null);

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }));

  async function handleSubmit() {
    // basic frontend validation
    if (!form.root_cause_category) return setError("Please select a root cause category");
    if (!form.problem_description.trim()) return setError("Problem description is required");
    if (!form.fix_applied.trim())         return setError("Fix applied is required");
    if (!form.prevention_steps.trim())    return setError("Prevention steps are required");
    if (!form.incident_start)             return setError("Incident start time is required");
    if (!form.incident_end)               return setError("Incident end time is required");
    if (form.incident_end <= form.incident_start) return setError("End time must be after start time");

    setError(null);
    setSubmitting(true);

    try {
      const res = await fetch(`${INCIDENT_URL}/incidents/${incident.id}/rca`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          work_item_id:         incident.id,
          root_cause_category:  form.root_cause_category,
          problem_description:  form.problem_description,
          fix_applied:          form.fix_applied,
          prevention_steps:     form.prevention_steps,
          incident_start:       new Date(form.incident_start).toISOString(),
          incident_end:         new Date(form.incident_end).toISOString(),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "RCA submission failed");

      setSuccess(data);

      // transition to CLOSED after RCA
      await fetch(`${INCIDENT_URL}/incidents/${incident.id}/state`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_state: "CLOSED" }),
      });

      setTimeout(onSuccess, 2000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (success) return (
    <div style={{ textAlign: "center", padding: "64px 0" }}>
      <div style={{ fontSize: 48, marginBottom: 16 }}>✓</div>
      <h2 style={{ fontFamily: "var(--sans)", fontSize: 24, fontWeight: 800, color: "var(--p2)", marginBottom: 8 }}>
        RCA Submitted
      </h2>
      <p style={{ color: "var(--text2)" }}>
        MTTR: <strong style={{ color: "var(--text)" }}>{success.mttr_minutes} minutes</strong>
      </p>
      <p style={{ color: "var(--text2)", fontSize: 13, marginTop: 8 }}>
        Incident closing and returning to feed...
      </p>
    </div>
  );

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontFamily: "var(--sans)", fontSize: 22, fontWeight: 800 }}>
            Root Cause Analysis
          </h1>
          <p style={{ color: "var(--text2)", fontSize: 12, marginTop: 2 }}>
            {incident?.component_id} · {incident?.priority} · Required to close incident
          </p>
        </div>
        <span className={`badge badge-${incident?.priority?.toLowerCase()}`}>
          {incident?.priority}
        </span>
      </div>

      {error && (
        <div className="error-box" style={{ marginBottom: 16 }}>⚠ {error}</div>
      )}

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 20 }}>

        {/* Root cause category */}
        <div className="form-group">
          <label className="form-label">ROOT CAUSE CATEGORY *</label>
          <select className="form-select" value={form.root_cause_category} onChange={set("root_cause_category")}>
            <option value="">Select category...</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {/* Problem description */}
        <div className="form-group">
          <label className="form-label">PROBLEM DESCRIPTION *</label>
          <textarea
            className="form-textarea"
            placeholder="What happened? Describe the incident clearly..."
            value={form.problem_description}
            onChange={set("problem_description")}
            style={{ minHeight: 100 }}
          />
        </div>

        {/* Fix applied */}
        <div className="form-group">
          <label className="form-label">FIX APPLIED *</label>
          <textarea
            className="form-textarea"
            placeholder="What was done to resolve the incident?"
            value={form.fix_applied}
            onChange={set("fix_applied")}
          />
        </div>

        {/* Prevention steps */}
        <div className="form-group">
          <label className="form-label">PREVENTION STEPS *</label>
          <textarea
            className="form-textarea"
            placeholder="How do we prevent this from happening again?"
            value={form.prevention_steps}
            onChange={set("prevention_steps")}
          />
        </div>

        {/* Time range */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div className="form-group">
            <label className="form-label">INCIDENT START *</label>
            <input
              type="datetime-local"
              className="form-input"
              value={form.incident_start}
              onChange={set("incident_start")}
            />
          </div>
          <div className="form-group">
            <label className="form-label">INCIDENT END *</label>
            <input
              type="datetime-local"
              className="form-input"
              value={form.incident_end}
              onChange={set("incident_end")}
            />
          </div>
        </div>

        {/* MTTR preview */}
        {form.incident_start && form.incident_end && form.incident_end > form.incident_start && (
          <div style={{
            background: "var(--bg3)", border: "1px solid var(--border)",
            borderRadius: 6, padding: "12px 16px",
            display: "flex", gap: 24, fontSize: 13
          }}>
            <span style={{ color: "var(--text2)" }}>Estimated MTTR:</span>
            <strong style={{ color: "var(--blue)" }}>
              {Math.round((new Date(form.incident_end) - new Date(form.incident_start)) / 60000)} minutes
            </strong>
          </div>
        )}

        {/* Submit */}
        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", paddingTop: 8, borderTop: "1px solid var(--border)" }}>
          <button className="btn btn-ghost" onClick={onBack} disabled={submitting}>
            Cancel
          </button>
          <button className="btn btn-danger" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Submitting..." : "Submit RCA & Close Incident"}
          </button>
        </div>
      </div>
    </div>
  );
}