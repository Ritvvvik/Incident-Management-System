// frontend/src/App.jsx
import { useState } from "react";
import LiveFeed from "./pages/LiveFeed";
import IncidentDetail from "./pages/IncidentDetail";
import RCAForm from "./pages/RCAForm";
import "./App.css";

export default function App() {
  const [page, setPage] = useState("feed");
  const [selectedIncident, setSelectedIncident] = useState(null);

  const goToDetail = (incident) => {
    setSelectedIncident(incident);
    setPage("detail");
  };

  const goToRCA = (incident) => {
    setSelectedIncident(incident);
    setPage("rca");
  };

  const goBack = () => {
    setPage("feed");
    setSelectedIncident(null);
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo" onClick={goBack}>
            <span className="logo-icon">⬡</span>
            <span className="logo-text">IMS</span>
            <span className="logo-sub">Incident Management</span>
          </div>
          <nav className="nav">
            <button className={page === "feed" ? "nav-btn active" : "nav-btn"} onClick={goBack}>
              Live Feed
            </button>
            {selectedIncident && (
              <>
                <span className="nav-sep">›</span>
                <button className={page === "detail" ? "nav-btn active" : "nav-btn"}
                  onClick={() => setPage("detail")}>
                  Incident #{selectedIncident.id?.slice(0, 8)}
                </button>
              </>
            )}
          </nav>
          <div className="header-status">
            <span className="pulse" />
            <span>Live</span>
          </div>
        </div>
      </header>

      <main className="main">
        {page === "feed" && <LiveFeed onSelect={goToDetail} />}
        {page === "detail" && (
          <IncidentDetail
            incident={selectedIncident}
            onBack={goBack}
            onRCA={goToRCA}
          />
        )}
        {page === "rca" && (
          <RCAForm
            incident={selectedIncident}
            onBack={() => setPage("detail")}
            onSuccess={goBack}
          />
        )}
      </main>
    </div>
  );
}