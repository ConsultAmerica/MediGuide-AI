"use client";

import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  FileText,
  FlaskConical,
  HelpCircle,
  Home as HomeIcon,
  LogOut,
  MessageCircleQuestion,
  Milestone,
  Pill,
  PlayCircle,
  Plus,
  ScanLine,
  Settings,
  ShieldCheck,
  Stethoscope,
  X,
} from "lucide-react";
import { BrandLogo } from "../../brand-logo";
import Link from "next/link";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { useAccount } from "./AuthGate";
import { serviceStateFrom } from "./serviceState";

function NavItem({
  href,
  label,
  icon: Icon,
  primary,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  primary?: boolean;
  onNavigate: (href: string) => void;
}) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <button
      className={`nav-item${active ? " active" : ""}${primary ? " nav-item-primary" : ""}`}
      aria-current={active ? "page" : undefined}
      onClick={() => onNavigate(href)}
    >
      <Icon size={17} />{label}
    </button>
  );
}

export function Sidebar({ onClose }: { onClose: () => void }) {
  const {
    setMobileNavOpen, clearSession, setPrivacyOpen, router,
    language, translateAnswer, health, setHealthOpen, setHelpOpen, setSettingsOpen,
  } = useWorkspaceContext();
  const serviceState = serviceStateFrom(health);

  function navigate(href: string) {
    router.push(href);
    setMobileNavOpen(false);
  }

  return (
    <aside className="sidebar workspace-sidebar">
      <div className="mobile-sidebar-head">
        <span>Navigate</span>
        <button className="icon-button" title="Close navigation" aria-label="Close navigation" onClick={onClose}><X size={18} /></button>
      </div>
      <div className="sidebar-brand-row">
        <div className="sidebar-brand-block">
          <BrandLogo variant="wordmark" tone="light" className="brand-logo-sidebar" />
        </div>
        <button className="icon-button sidebar-add" title="Upload a document" aria-label="Upload a document" onClick={() => navigate("/workspace/documents?action=upload")}>
          <Plus size={16} />
        </button>
      </div>
      <button className="new-conversation" onClick={() => { clearSession(); setMobileNavOpen(false); }}><Plus size={17} /> New</button>
      <button className="nav-item demo-nav-cta" onClick={() => navigate("/workspace/demo")}>
        <PlayCircle size={17} /> Try synthetic data
      </button>

      <div className="sidebar-label">OVERVIEW</div>
      <nav>
        <NavItem href="/workspace/home" label="Home" icon={HomeIcon} primary onNavigate={navigate} />
        <NavItem href="/workspace/timeline" label="Health Timeline" icon={Milestone} primary onNavigate={navigate} />
      </nav>

      <div className="sidebar-label">RECORDS</div>
      <nav>
        <NavItem href="/workspace/documents" label="Documents" icon={FileText} primary onNavigate={navigate} />
        <NavItem href="/workspace/labs" label="Labs" icon={FlaskConical} onNavigate={navigate} />
        <NavItem href="/workspace/imaging" label="Imaging" icon={ScanLine} onNavigate={navigate} />
        <NavItem href="/workspace/medications" label="Medications" icon={Pill} onNavigate={navigate} />
      </nav>

      <div className="sidebar-label">TOOLS</div>
      <nav>
        <NavItem href="/workspace/ask" label="Ask MediGuide" icon={MessageCircleQuestion} onNavigate={navigate} />
        <NavItem href="/workspace/visit" label="Visit Preparation" icon={Stethoscope} onNavigate={navigate} />
      </nav>

      <div className="sidebar-label knowledge-label">KNOWLEDGE</div>
      <nav>
        <NavItem href="/workspace/sources" label="Sources" icon={BookOpen} onNavigate={navigate} />
      </nav>

      <div className="sidebar-label knowledge-label">SYSTEM</div>
      <nav>
        <button className="nav-item" onClick={() => { setPrivacyOpen(true); setMobileNavOpen(false); }}><ShieldCheck size={17} /> Privacy</button>
        <NavItem href="/workspace/system" label="System Status" icon={Activity} onNavigate={navigate} />
      </nav>

      {/* Phones only: the header's secondary controls, which don't fit there. */}
      <div className="mobile-header-controls" aria-label="Workspace controls" role="group">
        <div className="sidebar-label">PREFERENCES</div>
        <label className="mobile-language">
          <span>Response language</span>
          <select className="language-select" value={language} onChange={(event) => void translateAnswer(event.target.value)}>
            <option>English</option><option>Spanish</option><option>French</option>
          </select>
        </label>
        <nav>
          <button className={`nav-item local-pill-row service-${serviceState.tone}`} onClick={() => { setHealthOpen(true); setMobileNavOpen(false); }}>
            <span className="service-dot" aria-hidden="true" /> Service status <small>{serviceState.label}</small>
          </button>
          <button className="nav-item" onClick={() => { setHelpOpen(true); setMobileNavOpen(false); }}><HelpCircle size={17} /> Help</button>
          <button className="nav-item" onClick={() => { setSettingsOpen(true); setMobileNavOpen(false); }}><Settings size={17} /> Settings</button>
        </nav>
      </div>

      <AccountFooter />
    </aside>
  );
}

function AccountFooter() {
  const { user, signOut } = useAccount();
  const label = user.is_guest ? "Guest workspace" : user.display_name || user.email;
  return (
    <div className="sidebar-footer sidebar-account">
      <div className="sidebar-account-who">
        <strong title={user.email || undefined}>{label}</strong>
        <small>{user.is_guest ? "Only you can see these records" : user.email}</small>
      </div>
      {user.is_guest && (
        <Link className="sidebar-account-save" href="/signin?mode=register&next=/workspace/home">
          Save to an account
        </Link>
      )}
      <button type="button" className="quiet-button sidebar-account-signout" onClick={() => void signOut()}>
        <LogOut size={15} aria-hidden /> Sign out
      </button>
    </div>
  );
}
