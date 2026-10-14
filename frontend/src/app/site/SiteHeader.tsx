"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Menu, X } from "lucide-react";
import { BrandLogo } from "../brand-logo";

const NAV = [
  { href: "#workflow", label: "How it works" },
  { href: "#features", label: "Features" },
  { href: "#imaging", label: "Imaging" },
  { href: "#trust", label: "Trust & safety" },
];

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const firstLink = useRef<HTMLAnchorElement>(null);

  // A sentinel at the top of the page flips the header's surface; no
  // scroll listener runs on every frame.
  useEffect(() => {
    const sentinel = document.getElementById("top-sentinel");
    if (!sentinel || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(([entry]) => setScrolled(!entry.isIntersecting));
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    firstLink.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMenu();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  function closeMenu() {
    setMenuOpen(false);
    menuButton.current?.focus();
  }

  return (
    <header className={`site-header${scrolled ? " is-scrolled" : ""}${menuOpen ? " menu-open" : ""}`}>
      <div className="site-container site-header-inner">
        <Link href="/" className="site-brand" aria-label="MediGuide home">
          <BrandLogo variant="wordmark" priority />
        </Link>

        <nav className="site-nav" aria-label="Primary">
          {NAV.map((item) => (
            <a key={item.href} href={item.href}>{item.label}</a>
          ))}
        </nav>

        <div className="site-header-actions">
          <Link href="/signin" className="site-link-quiet">Sign in</Link>
          <Link href="/workspace/home" className="site-btn site-btn-lime site-btn-sm" prefetch={false}>
            Open workspace <ArrowRight size={15} aria-hidden="true" />
          </Link>
        </div>

        <button
          ref={menuButton}
          type="button"
          className="site-menu-button"
          aria-expanded={menuOpen}
          aria-controls="site-mobile-menu"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          onClick={() => (menuOpen ? closeMenu() : setMenuOpen(true))}
        >
          {menuOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      <div id="site-mobile-menu" className="site-mobile-menu" hidden={!menuOpen}>
        <nav aria-label="Mobile">
          {NAV.map((item, index) => (
            <a key={item.href} ref={index === 0 ? firstLink : undefined} href={item.href} onClick={() => setMenuOpen(false)}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="site-mobile-actions">
          <Link href="/workspace/documents?action=sample" className="site-btn site-btn-primary" prefetch={false}>
            Try it with synthetic data
          </Link>
          <Link href="/signin" className="site-btn site-btn-secondary">Sign in</Link>
        </div>
      </div>
    </header>
  );
}
