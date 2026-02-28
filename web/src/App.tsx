import { NavLink, Route, Routes, useLocation } from "react-router-dom";
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
  const location = useLocation();
  const isPlayerDetail = location.pathname.startsWith("/players/");
  const navItems = [
    { to: "/", label: "Discover", icon: "◆", subtitle: "Today’s streamer board and trends" },
    { to: "/explore", label: "Explore", icon: "●", subtitle: "Filter players by windowed analytics" },
    { to: "/scans", label: "Scans", icon: "≣", subtitle: "Evaluate custom rule-based scans" },
    { to: "/leagues", label: "Leagues", icon: "◈", subtitle: "Manage scoring profiles" },
    { to: "/settings", label: "Settings", icon: "⚙", subtitle: "Account and sync controls" },
  ];
  const active = navItems.find((item) => {
    if (item.to === "/") return location.pathname === "/";
    if (item.to === "/explore" && isPlayerDetail) return true;
    return location.pathname.startsWith(item.to);
  }) ?? navItems[0];

  return (
    <main className="app-shell">
      <header className="top-header">
        <small className="eyebrow">Forecheck v2</small>
        <h1>{isPlayerDetail ? "Player Detail" : active.label}</h1>
        <p className="muted">{isPlayerDetail ? "Window comparisons and game logs" : active.subtitle}</p>
      </header>

      <section className="page-content">{children}</section>

      <nav className="tabbar">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `tab-link ${isActive || (item.to === "/explore" && isPlayerDetail) ? "active" : ""}`
            }
          >
            <span className="tab-icon">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </main>
  );
}

function BootShell({ children }: { children: ReactNode }) {
  return (
    <main className="app-shell boot-shell">
      <header className="top-header">
        <small className="eyebrow">Forecheck v2</small>
        <h1>Setup</h1>
        <p className="muted">Self-hosted fantasy hockey analytics</p>
      </header>
      <section className="page-content">{children}</section>
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
      <BootShell>
        <section className="card ios-card">
          <h2>Loading setup status...</h2>
          {setupError ? <p className="error">{setupError}</p> : null}
        </section>
      </BootShell>
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
