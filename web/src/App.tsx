import { NavLink, Route, Routes } from "react-router-dom";
import { ReactNode, useEffect, useState } from "react";

import { clearSession, fetchSetupStatus, loadSession, saveSession } from "./api";
import type { AuthSession, SetupStatus } from "./types";

import DiscoverPage from "./pages/DiscoverPage";
import ExplorePage from "./pages/ExplorePage";
import LeaguesPage from "./pages/LeaguesPage";
import LoginPage from "./pages/LoginPage";
import PlayerDetailPage from "./pages/PlayerDetailPage";
import ScansPage from "./pages/ScansPage";
import SettingsPage from "./pages/SettingsPage";
import SetupPage from "./pages/SetupPage";

function AppLayout({ children }: { children: ReactNode }) {
  return (
    <main className="layout">
      <header className="card">
        <h1>Forecheck v2</h1>
        <p className="muted">Self-hosted fantasy hockey analytics</p>
        <nav className="nav">
          <NavLink to="/">Discover</NavLink>
          <NavLink to="/explore">Explore</NavLink>
          <NavLink to="/scans">Scans</NavLink>
          <NavLink to="/leagues">Leagues</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>
      {children}
    </main>
  );
}

export default function App() {
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const [session, setSession] = useState<AuthSession | null>(() => loadSession());
  const [setupError, setSetupError] = useState<string | null>(null);

  async function refreshSetupStatus() {
    try {
      const status = await fetchSetupStatus();
      setSetupStatus(status);
      setSetupError(null);
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : "Failed to load setup status");
    }
  }

  useEffect(() => {
    void refreshSetupStatus();
  }, []);

  function handleSession(next: AuthSession | null) {
    setSession(next);
    if (next) {
      saveSession(next);
    } else {
      clearSession();
    }
  }

  if (!setupStatus) {
    return (
      <main className="layout">
        <section className="card">
          <h1>Forecheck v2</h1>
          <p className="muted">Loading setup status...</p>
          {setupError ? <p className="error">{setupError}</p> : null}
        </section>
      </main>
    );
  }

  if (setupStatus.setup_required) {
    return <SetupPage onComplete={refreshSetupStatus} />;
  }

  if (!session) {
    return <LoginPage onLogin={handleSession} />;
  }

  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<DiscoverPage />} />
        <Route path="/explore" element={<ExplorePage />} />
        <Route path="/players/:playerId" element={<PlayerDetailPage />} />
        <Route path="/scans" element={<ScansPage session={session} onSession={handleSession} />} />
        <Route path="/leagues" element={<LeaguesPage session={session} onSession={handleSession} />} />
        <Route path="/settings" element={<SettingsPage session={session} onSession={handleSession} />} />
      </Routes>
    </AppLayout>
  );
}
