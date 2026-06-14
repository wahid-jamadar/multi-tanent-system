# 🚀 Splash / Logo Loading Screen — Design & Implementation Plan

> **Project:** BatchHost-Pro  
> **Feature:** Splash + Logo Loading Screen  
> **Status:** Implemented  
> **Date:** 2026-05-12

---

## 1. Overview

A **full-screen splash/logo screen** that appears once during the initial page load of the application — specifically on the **login page** (`/login`). It creates a premium first impression by showcasing the BatchHost-Pro brand with smooth animations before revealing the login form.

> **Note:** The splash screen is a **client-side overlay**, not a separate page or route. It lives entirely inside `login.html` and is driven by CSS animations + a small JS timer.

---

## 2. How It Will Appear (Visual Design)

### 2.1 Layout

```
┌─────────────────────────────────────────────────┐
│                                                 │
│              (dark background)                  │
│          subtle animated grid lines             │
│                                                 │
│                ┌───────────┐                    │
│                │  LOGO     │  ← BatchHost-Pro   │
│                │  (image)  │     logo.png        │
│                └───────────┘                    │
│                                                 │
│           B a t c h H o s t P r o              │
│        BATCH FILE MANAGEMENT SYSTEM             │
│                                                 │
│         ╔══════════════════════╗                │
│         ║  ████████░░░░░░░░░  ║ ← progress bar │
│         ╚══════════════════════╝                │
│                                                 │
│           Initializing system...                │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 2.2 Visual Elements

| Element | Description |
|---|---|
| **Background** | Full viewport, matches app dark theme (`#0B1220`) with the existing login background image blurred behind it at low opacity |
| **Grid Overlay** | Subtle animated grid lines (reuses existing `.bg-grid` pattern from `login.html`) at 4% opacity |
| **Logo** | The `BatchHost-Pro_logo.png` (monitors/folders icon) centered, ~120px height, with a soft blue glow pulsing behind it |
| **Brand Text** | "BatchHost" in white (`#E5E7EB`) + "Pro" in accent blue (`#3B82F6`), using the `Inter` font at 800 weight, 32px |
| **Tagline** | "BATCH FILE MANAGEMENT SYSTEM" in muted gray (`#6B7280`), uppercase, letter-spacing 0.12em, 12px, `JetBrains Mono` |
| **Progress Bar** | Slim horizontal bar (4px height, 280px width) with a gradient fill animating left-to-right — accent blue → purple (`#3B82F6 → #8B5CF6`) |
| **Status Text** | Below progress bar, cycling through status messages in monospace: "Initializing system…", "Loading modules…", "Preparing dashboard…" |
| **Glow Effect** | A radial gradient glow circle behind the logo, softly pulsing (blue at 15% opacity) |

### 2.3 Color Palette Used

```css
--splash-bg:       #0B1220     /* Same as app --bg */
--splash-text:     #E5E7EB     /* Same as --text */
--splash-accent:   #3B82F6     /* Same as --accent */
--splash-muted:    #6B7280     /* Same as --text3 */
--splash-purple:   #8B5CF6     /* Same as --purple */
--splash-glow:     rgba(59, 130, 246, 0.15)
```

---

## 3. How It Will Work (Animation Phases)

The splash screen runs for a total of **~3 seconds** and has 4 phases:

### Phase 1 — Logo Entrance (0 – 0.8s)
- Logo scales from `0.85` → `1.0` and fades from `0` → `1` opacity
- Blue glow pulse begins behind logo (infinite loop, subtle)
- Uses `cubic-bezier(0.16, 1, 0.3, 1)` for a premium spring-like feel

### Phase 2 — Text & Shimmer (0.4 – 1.5s)
- Brand text ("BatchHostPro") fades in from below (translateY 15px → 0)
- Tagline fades in 200ms after the brand text
- A shimmer/shine effect sweeps across the brand text once (CSS gradient animation)

### Phase 3 — Progress Bar Fill (0.8 – 2.5s)
- The progress bar appears and fills from 0% → 100% width
- Status text cycles every ~600ms: "Initializing system…" → "Loading modules…" → "Preparing dashboard…"
- Progress bar has a glowing edge effect as it fills

### Phase 4 — Fade Out & Reveal (2.5 – 3.0s)
- Entire splash overlay fades to `opacity: 0` and scales slightly up (`1.02`)
- After animation completes, the overlay element is removed from DOM via JS
- Login form is now fully visible and interactive beneath

### Timing Diagram

```
Time (s):  0.0    0.4    0.8    1.5    2.0    2.5    3.0
           │      │      │      │      │      │      │
Logo:      ╠══════╝      │      │      │      │      │
Text:             ╠══════╧══════╝      │      │      │
Progress:                ╠══════╧══════╧══════╝      │
Fade-out:                                    ╠══════╝
```

---

## 4. Session-Based Display Control

> **Important:** The splash screen should only appear **once per browser session** to avoid annoying returning users.

| Scenario | Splash Shows? | Mechanism |
|---|---|---|
| First visit to `/login` in a session | ✅ Yes | `sessionStorage` key `splash_shown` is absent |
| Refresh `/login` page | ❌ No | `sessionStorage` key `splash_shown` exists |
| Logout → back to `/login` | ❌ No | Session storage persists until tab/window closes |
| New browser tab to `/login` | ✅ Yes | Fresh session storage |
| Close browser → reopen `/login` | ✅ Yes | Session storage cleared on close |

**Implementation:**
```javascript
// In login.html <script>
if (!sessionStorage.getItem('splash_shown')) {
    showSplash();
    sessionStorage.setItem('splash_shown', 'true');
} else {
    removeSplashInstantly();
}
```

---

## 5. Implementation Architecture

### 5.1 Where It Lives

The splash is **entirely contained within `login.html`** — no new templates, no new routes.

```
login.html
├── <div id="splashOverlay">       ← NEW: Full-screen overlay (z-index: 10000)
│   ├── .splash-bg-grid            ← Animated background grid
│   ├── .splash-glow               ← Blue glow behind logo
│   ├── .splash-logo               ← <img> of BatchHost-Pro_logo.png
│   ├── .splash-brand              ← "BatchHostPro" text
│   ├── .splash-tagline            ← "BATCH FILE MANAGEMENT SYSTEM"
│   ├── .splash-progress-wrap      ← Progress bar container
│   │   └── .splash-progress-fill  ← Animated fill bar
│   └── .splash-status             ← Cycling status text
│
├── <div class="bg-grid">          ← Existing login background
├── <div class="card">             ← Existing login form
│   └── ...
└── <script>                       ← Existing + new splash logic
```

### 5.2 Files Changed

| File | Change Type | Description |
|---|---|---|
| `templates/login.html` | **Modified** | Add splash overlay HTML, CSS, and JS |
| `server.py` | **No changes** | No backend changes needed — the splash is fully client-side |
| `images/` | **No changes** | Reuses existing `BatchHost-Pro_logo.png` |

> **Tip:** This is a **zero-impact** change from a backend perspective. No routes, no APIs, no server-side session logic is modified. The splash is pure frontend.

### 5.3 HTML Structure (Preview)

```html
<!-- Splash Screen Overlay -->
<div id="splashOverlay" class="splash-overlay">
    <div class="splash-bg-grid"></div>
    <div class="splash-glow"></div>
    <div class="splash-content">
        <img src="/images/BatchHost-Pro_logo.png" alt="BatchHost-Pro" class="splash-logo">
        <div class="splash-brand">
            BatchHost<span>Pro</span>
        </div>
        <div class="splash-tagline">BATCH FILE MANAGEMENT SYSTEM</div>
        <div class="splash-progress-wrap">
            <div class="splash-progress-fill"></div>
        </div>
        <div class="splash-status">Initializing system…</div>
    </div>
</div>
```

### 5.4 CSS Key Styles (Preview)

```css
.splash-overlay {
    position: fixed;
    inset: 0;
    z-index: 10000;
    background: #0B1220;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    transition: opacity 0.5s ease, transform 0.5s ease;
}

.splash-overlay.fade-out {
    opacity: 0;
    transform: scale(1.02);
    pointer-events: none;
}

.splash-logo {
    height: 120px;
    width: auto;
    animation: splashLogoIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    filter: drop-shadow(0 0 30px rgba(59, 130, 246, 0.3));
}

@keyframes splashLogoIn {
    from { opacity: 0; transform: scale(0.85); }
    to   { opacity: 1; transform: scale(1);    }
}

.splash-brand {
    font-family: 'Inter', sans-serif;
    font-size: 32px;
    font-weight: 800;
    color: #E5E7EB;
    opacity: 0;
    animation: splashTextIn 0.6s ease 0.4s forwards;
}

.splash-brand span {
    color: #3B82F6;
}

.splash-progress-fill {
    height: 4px;
    background: linear-gradient(90deg, #3B82F6, #8B5CF6);
    border-radius: 2px;
    width: 0%;
    animation: splashFill 1.7s ease 0.8s forwards;
}

@keyframes splashFill {
    to { width: 100%; }
}
```

### 5.5 JavaScript Logic (Preview)

```javascript
document.addEventListener('DOMContentLoaded', () => {
    const overlay = document.getElementById('splashOverlay');
    if (!overlay) return;

    // Skip splash if already shown this session
    if (sessionStorage.getItem('splash_shown')) {
        overlay.remove();
        return;
    }

    sessionStorage.setItem('splash_shown', 'true');

    // Cycle status messages
    const statusEl = overlay.querySelector('.splash-status');
    const messages = ['Initializing system…', 'Loading modules…', 'Preparing dashboard…'];
    let msgIndex = 0;
    const msgInterval = setInterval(() => {
        msgIndex = (msgIndex + 1) % messages.length;
        if (statusEl) statusEl.textContent = messages[msgIndex];
    }, 600);

    // Fade out and remove after animation completes
    setTimeout(() => {
        clearInterval(msgInterval);
        overlay.classList.add('fade-out');
        setTimeout(() => overlay.remove(), 500);
    }, 2500);
});
```

---

## 6. User Experience Flow

```
User opens browser
    └─→ Navigates to BatchHost-Pro URL
        └─→ Is this the first visit this session?
            ├─→ YES → 🎬 Splash Screen (~3 seconds)
            │           └─→ Splash fades out
            │               └─→ Login Form visible
            └─→ NO  → Login Form visible immediately
                        └─→ User enters credentials
                            └─→ Click "Sign In"
                                ├─→ Success → Redirect to /dashboard
                                └─→ Failure → Error flash message
```

---

## 7. Theme Support

The splash screen respects the user's saved theme preference:

| Theme | Splash Background | Text Color | Accent |
|---|---|---|---|
| **Dark** (default) | `#0B1220` | `#E5E7EB` | `#3B82F6` |

The theme is read from `localStorage.getItem('bm-theme')` at load time (before splash renders), matching the existing theme system in `login.html`.

---

## 8. Responsive Behavior

| Viewport | Logo Size | Brand Text | Progress Bar Width |
|---|---|---|---|
| Desktop (>768px) | 120px | 32px | 280px |
| Tablet (768px) | 100px | 28px | 240px |
| Mobile (<480px) | 80px | 24px | 200px |

All elements remain centered. The layout uses flexbox with `align-items: center` and `justify-content: center`.

---

## 9. Accessibility Considerations

- Splash overlay has `aria-hidden="true"` and `role="presentation"` since it's decorative
- No keyboard traps — the overlay is non-interactive
- Status text uses `aria-live="polite"` for screen readers
- Animations respect `prefers-reduced-motion`:
  ```css
  @media (prefers-reduced-motion: reduce) {
      .splash-overlay * {
          animation-duration: 0.01ms !important;
      }
      .splash-overlay {
          transition-duration: 0.01ms !important;
      }
  }
  ```

---

## 10. Performance Impact

| Metric | Impact |
|---|---|
| **Additional DOM elements** | 7 elements (removed after 3s) |
| **Additional CSS** | ~60 lines of scoped styles |
| **Additional JS** | ~25 lines |
| **Network requests** | 0 (reuses already-loaded logo image) |
| **Time to interactive** | No impact — login form is rendered behind overlay, immediately usable after splash |

> **Tip:** Since the login form loads in parallel behind the splash, the actual time-to-interactive is **unchanged**. The splash is purely cosmetic and does not delay functionality.

---

## 11. File Change Summary

```diff
  templates/
    login.html            ← MODIFIED (add splash overlay + styles + JS)
  
  server.py               ← NO CHANGES
  images/                 ← NO CHANGES  
  templates/base.html     ← NO CHANGES
  templates/dashboard.html← NO CHANGES
```

**Estimated implementation time:** ~30 minutes

---

## 12. Final Decisions

| Decision | Choice |
|---|---|
| **Duration** | 3 seconds ✅ |
| **Status messages** | Default set ("Initializing system…", "Loading modules…", "Verifying configuration…", "Preparing dashboard…") ✅ |
| **Sound** | No audio ✅ |
| **Skip button** | No skip button ✅ |
| **Theme** | Always dark mode (forced, ignores saved preference) ✅ |

---

> **Implementation completed** on 2026-05-12. Splash screen added to `templates/login.html` with floating particles, shimmer effect, gradient progress bar, and session-based display control.
