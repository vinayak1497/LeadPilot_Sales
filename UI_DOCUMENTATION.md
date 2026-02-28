# LeadPilot — UI Documentation

> Describes every screen, navigation path, element, button, text label, and interactive component in the current application UI.

---

## Table of Contents

1. [Design System](#1-design-system)
2. [Navigation & Routing](#2-navigation--routing)
3. [Screen: Landing Page (`/`)](#3-screen-landing-page-)
4. [Screen: Dashboard (`/dashboard`)](#4-screen-dashboard-dashboard)
5. [Screen: Login (`/auth/login`)](#5-screen-login-authlogin)
6. [Screen: Sign Up (`/auth/signup`)](#6-screen-sign-up-authsignup)
7. [Screen: Error Page](#7-screen-error-page)
8. [Screen: Architecture Diagram (`/architecture_diagram`)](#8-screen-architecture-diagram-architecture_diagram)
9. [Modals & Overlays](#9-modals--overlays)
10. [Shared Components](#10-shared-components)

---

## 1. Design System

### Color Palette

| Token | Value | Usage |
|---|---|---|
| `--primary-color` | `#2563eb` | Primary buttons, links, active states |
| `--primary-dark` | `#1d4ed8` | Button hover state |
| `--primary-light` | `#dbeafe` | Light background accents |
| `--secondary-color` | `#7c3aed` | Gradient accents (auth screens) |
| `--success-color` | `#16a34a` | Success badges, positive indicators |
| `--warning-color` | `#d97706` | Warning states |
| `--danger-color` | `#dc2626` | Error states, logout |
| `--gray-50` → `--gray-900` | `#f8fafc` → `#0f172a` | Full gray scale |
| `--text-primary` | `#0f172a` | Main text |
| `--text-secondary` | `#475569` | Supporting text |
| `--text-muted` | `#94a3b8` | Placeholder / secondary labels |
| `--bg-primary` | `#f8fafc` | Page background |
| `--card-bg` | `#ffffff` | Card background |

### Typography

- **Font**: `Inter` (loaded via Google Fonts on dashboard; system font on other pages)
- **Font sizes**: 11px (micro labels) → 2rem (page headings)
- **Font weights**: 400 (normal), 500 (medium), 600 (semibold), 700 (bold)

### Shadow System

| Token | Usage |
|---|---|
| `--shadow-sm` | Subtle card lift |
| `--shadow-md` | Standard cards |
| `--shadow-lg` | Elevated panels |
| `--shadow-xl` | Modals |

### Border Radii

| Token | Value |
|---|---|
| `--border-radius` | `8px` |
| `--border-radius-lg` | `12px` |
| `--border-radius-xl` | `16px` |

### Animated Background

All pages share **8 floating `.particle` divs** that animate continuously in the background, providing subtle movement behind page content.

---

## 2. Navigation & Routing

### Page Routes

| URL | Method | Template | Description |
|---|---|---|---|
| `/` | GET | `index.html` | Landing page — enter city to start |
| `/start_lead_finding` | POST | → redirect to `/dashboard` | Submits city, starts AI agents |
| `/dashboard` | GET | `dashboard.html` | Live pipeline dashboard |
| `/auth/login` | GET | `login.html` | Clerk-powered sign-in |
| `/auth/signup` | GET | `signup.html` | Clerk-powered sign-up |
| `/auth/logout` | GET | — | Clears session, redirects to `/` |
| `/architecture_diagram` | GET | `architecture_diagram.html` | System architecture visualization |
| `/reset` | POST | — | Resets all lead data |
| `/test_ui` | GET | `test_ui.html` | Internal UI test page |

### API Endpoints (used internally by JS)

| URL | Method | Purpose |
|---|---|---|
| `/api/businesses` | GET | Fetch all current businesses |
| `/api/leads/history` | GET | Lead history |
| `/api/status` | GET | Agent running status |
| `/send_to_sdr` | POST | Queue business for SDR agent |
| `/research_business/{id}` | GET | AI research for a business |
| `/generate_proposal/{id}` | POST | Generate sales proposal |
| `/trigger_lead_manager` | POST | Manually trigger lead manager |
| `/api/human-input` | GET / POST | Interact with human-in-the-loop requests |
| `/agent_callback` | POST | Internal agent event ingestion |

### WebSocket

- **Path**: `ws://{host}/ws`
- Delivers real-time events: `initial_state`, `business_update`, `agent_update`, `human_input_required`

---

## 3. Screen: Landing Page (`/`)

**File**: `ui_client/templates/index.html`  
**Style**: `ui_client/static/css/style.css`

### Layout Structure

```
[Particles Background]
[.container]
  ├── [.header]           ← Logo + Tagline + Value Props + Auth Actions
  ├── [.main-card]        ← City Input Form + How It Works + Trust Indicators
  └── [.features]         ← 3 Feature Highlight Cards
```

---

### Header Section (`.header`)

#### Logo Block (`.logo`)
| Element | Type | Content |
|---|---|---|
| `.logo-icon-wrapper` | Icon container | `fa-rocket` icon |
| `h1` | Heading | **"LeadPilot"** |
| `.logo-tagline` | Span | `"Powered by AI"` |

#### Subtitle
- `<p class="subtitle">` — **"Transform Your Lead Generation with Intelligent AI Agents"**
- Animated with typewriter effect on page load (types character-by-character after 500ms delay)

#### Value Props (`.value-props`)
Three inline badges displayed horizontally:

| Icon | Label |
|---|---|
| `fa-bolt` | **Automated** |
| `fa-brain` | **AI-Driven** |
| `fa-chart-line` | **Results-Focused** |

#### Header Action Buttons (`.header-actions`)

**Guest (not signed in):**
| Button | Action | Style |
|---|---|---|
| `Login / Sign Up` (icon: `fa-user`) | `window.location.href='/auth/login'` | `.auth-btn` — outlined primary |

**Signed-in user (Clerk active):**
| Element | Content | Action |
|---|---|---|
| `.user-btn` | Avatar + Name + `fa-chevron-down` | Toggles `.user-dropdown` |
| Dropdown — User info | Name (bold) + Email (muted) | Display only |
| Dropdown item — `Manage Account` | `fa-user-cog` | Opens Clerk user profile modal |
| Dropdown item — `Sign Out` | `fa-sign-out-alt` | Calls `Clerk.signOut()` → redirects `/` |

**Secondary Button (always visible):**
| Button | Action | Style |
|---|---|---|
| `View Architecture` (icon: `fa-project-diagram`) | `window.open('/architecture_diagram', '_blank')` | `.architecture-btn` |

---

### Main Card (`.main-card`)

#### Card Header
| Element | Content |
|---|---|
| `.header-icon-pulse` | `fa-location-dot` pulsing icon |
| `h2` | **"Discover Your Next Customers"** |
| `.header-subtitle` | `"Enter any city and watch our AI agents find qualified leads for you"` |

#### Search Form (`.search-form`)
- Form action: `POST /start_lead_finding`

| Element | Type | Details |
|---|---|---|
| `label[for="city"]` | Label | `fa-map-marker-alt` icon + **"Target Location"** |
| `#city` | Text input | Placeholder: `"San Francisco, New York, Austin, London..."`, `maxlength=100`, `required`, auto-capitalizes words on input |
| `.input-hint` | Hint text | `"Our AI will automatically discover and qualify businesses in this area"` |
| Submit button `.run-button` | Primary button | `fa-rocket` + **"Launch AI Agents"** — spins to `"Launching Agents..."` on submit |

#### How It Works Section (`.process-info`)

Heading: `fa-wand-magic-sparkles` + **"How It Works"**

Four process steps displayed as a vertical list:

| Step | Icon | Title | Description |
|---|---|---|---|
| 1 | `fa-search` | **Discover Leads** | `"AI scouts find businesses matching your criteria"` |
| 2 | `fa-user-tie` | **Smart Engagement** | `"Intelligent agents qualify and engage prospects"` |
| 3 | `fa-globe` | **Create Websites** | `"AI generates custom websites through Google IDX"` |
| 4 | `fa-calendar-check` | **Book Meetings** | `"Convert hot leads into scheduled appointments"` |

#### Trust Indicators (`.trust-indicators`)

Three inline badges:

| Icon | Label |
|---|---|
| `fa-shield-halved` | **Enterprise Security** |
| `fa-clock` | **Real-time Processing** |
| `fa-crown` | **Premium AI Models** |

---

### Features Section (`.features`)

Three feature cards displayed in a row:

| Icon | Title | Description |
|---|---|---|
| `fa-robot` | **Autonomous Agents** | `"Multi-agent AI system handles everything automatically"` |
| `fa-bullseye` | **Precision Targeting** | `"Find exactly the right businesses for your service"` |
| `fa-chart-pie` | **Complete Analytics** | `"Track every interaction and conversion in real-time"` |

---

## 4. Screen: Dashboard (`/dashboard`)

**File**: `ui_client/templates/dashboard.html`  
**Style**: `ui_client/static/css/dashboard.css`  
**Script**: `ui_client/static/js/dashboard.js`

### Layout Structure

```
[Particles Background]
[.dashboard-container]
  ├── [.dashboard-header]      ← Logo + City Badge + Status + Buttons + Auth
  ├── [.stats-bar]             ← 4 Metric Counters
  ├── [.agent-columns]         ← 4 Kanban-style Agent Columns
  └── [.activity-log]          ← Collapsible Event Log
[Loading Overlay]
[Modal: Business Research]
[Modal: SDR Dialog]
[Modal: Human Input / Google IDX]
```

---

### Dashboard Header (`.dashboard-header`)

#### Left Side (`.header-left`)
| Element | Content |
|---|---|
| Logo `fa-rocket` icon | Always visible |
| `h1` | **"LeadPilot"** |
| `.current-target` (conditional) | `fa-map-marker-alt` + current city name (shown only when a city is active) |

#### Right Side (`.header-right`)

| Element | Content / Action |
|---|---|
| `.status-indicator` + `.status-light` | Dot: green `active` when running, gray `idle` when ready. Label: **"Processing"** or **"Ready"** |
| `.reset-btn` | `fa-refresh` + **"New Search"** — calls `resetDashboard()` → `POST /reset` |
| `#auth-container` | Same Clerk-aware auth button/user menu as landing page (see §3 header) |
| Debug button (amber) | `fa-globe` + **"Test Human Input"** — calls `testHumanInputDialog()` (dev utility) |

---

### Stats Bar (`.stats-bar`)

Four metric tiles displayed horizontally:

| ID | Label | What it counts |
|---|---|---|
| `#total-businesses` | **Total Leads** | All businesses in pipeline |
| `#engaged-count` | **Engaged** | Businesses in `engaged` status |
| `#converting-count` | **Converting** | Businesses in `converting` status |
| `#meetings-count` | **Meetings Scheduled** | Businesses in `meeting_scheduled` status — tile has `.hot` highlight |

Values update in real-time via WebSocket events.

---

### Agent Columns (`.agent-columns`)

Four columns rendered as a horizontal Kanban board. Each column has:
- **Column header** with agent icon, name, subtitle, and live status dot
- **Column content** area (`.column-content`) with scrollable business cards

#### Column 1 — Lead Finder

| Property | Value |
|---|---|
| Icon | `fa-search` |
| Title | **Lead Finder** |
| Subtitle | `"Discovering potential businesses"` |
| Status ID | `#lead-finder-status` |
| Content ID | `#lead-finder-content` |

**Business cards shown**: status = `found`  
**Badge label**: `Found` (`.status-found` — blue)  
**Click behavior**: Opens AI Business Research modal

#### Column 2 — SDR Agent

| Property | Value |
|---|---|
| Icon | `fa-user-tie` |
| Title | **SDR Agent** |
| Subtitle | `"Engaging and qualifying prospects"` |
| Status ID | `#sdr-status` |
| Content ID | `#sdr-content` |

**Email Tracking Bar** (`.email-tracking-bar`) — always visible above cards:
| Element | Content |
|---|---|
| `fa-envelope-open-text` icon | Blue color |
| `#email-tracking-status` | **"Email tracking active"** |
| Button | `fa-sync-alt` + **"Check Replies"** — calls `dashboardManagerInstance.checkEmailsNow()` |

**Business cards shown**: status = `contacted`, `engaged`, `not_interested`, `no_response`

| Status | Badge Label | Badge Color |
|---|---|---|
| `contacted` | **Contacted** | Gray |
| `engaged` | **Engaged** | Green |
| `not_interested` | **Not Interested** | Red |
| `no_response` | **No Response** | Yellow/amber |

#### Column 3 — Lead Manager

| Property | Value |
|---|---|
| Icon | `fa-chart-line` |
| Title | **Lead Manager** |
| Subtitle | `"Converting to hot leads"` |
| Status ID | `#lead-manager-status` |
| Content ID | `#lead-manager-content` |
| Header click | `triggerLeadManager()` → `POST /trigger_lead_manager` (cursor: pointer) |

**Business cards shown**: status = `converting`  
**Card style**: `.hot-lead` — highlighted hot lead card  
**Card extras**: `fa-fire` hot icon before business name  
**Badge label**: `Converting` (`.status-converting` — orange)

#### Column 4 — Calendar

| Property | Value |
|---|---|
| Icon | `fa-calendar-alt` |
| Title | **Calendar** |
| Subtitle | `"Scheduled meetings"` |
| Status ID | `#calendar-status` |
| Content ID | `#meeting-scheduled-content` |

**Business cards shown**: status = `meeting_scheduled`  
**Card style**: `.meeting-card`  
**Card extras**: `fa-handshake` meeting icon before business name  
**Badge label**: `Meeting Scheduled` (`.status-meeting-scheduled` — green)  
**Date field**: Shows `updated_at` formatted timestamp

---

### Business Card Structure

Each business card (`.business-card.compact`) contains:

| Element | Content | Notes |
|---|---|---|
| `h4` | Business name | Bold |
| `.status-badge` | Status label | Color-coded (see above) |
| `fa-map-marker-alt` + span | City name | Always shown |
| `fa-phone` + span | Phone number | Shown only if exists |
| `fa-envelope` + span | Email (truncated to 20 chars + `...`) | Shown only if exists |
| `.compact-notes` `fa-sticky-note` | Last note (truncated to 50 chars) | SDR/Lead Manager/Calendar only |

**Clickable cards** (Lead Finder column): gain `.clickable` class when business data is loaded.  
- Cursor: `pointer`  
- Hover: blue border + `0 0 0 3px rgba(37,99,235,0.1)` ring  
- Click: opens **AI Business Research Modal**

---

### Activity Log (`.activity-log`)

Positioned at bottom of dashboard, collapsible.

| Element | Content |
|---|---|
| `h3` heading | `fa-history` + **"Recent Activity"** |
| Toggle button `.toggle-log` | `fa-chevron-up` / `fa-chevron-down` — calls `toggleLog()` |
| `#activity-log` | Scrollable list of log entries |

Each log entry (`.log-entry`) contains:
- `.log-time` — formatted timestamp
- `.log-agent` — agent name (title-cased)
- `.log-message` — event message text

---

## 5. Screen: Login (`/auth/login`)

**File**: `ui_client/templates/login.html`  
**Style**: `ui_client/static/css/style.css` + inline styles

### Layout

```
[Particles Background]
[.auth-container]
  └── [.auth-card]
        ├── [Back to Home link]
        ├── [.auth-header]    ← Logo + Subtitle
        ├── [#loading-state]  ← Spinner (hidden after Clerk loads)
        ├── [#clerk-sign-in]  ← Clerk SignIn component (mounted dynamically)
        └── [.auth-footer]    ← "Powered by Clerk" link
```

### Elements

| Element | Content |
|---|---|
| `.back-link` | `fa-arrow-left` + **"Back to Home"** → navigates to `/` |
| `.auth-logo` icon | `fa-rocket` (gradient: `#6366f1` → `#8b5cf6`) |
| `.auth-logo h1` | **"LeadPilot"** |
| `.auth-subtitle` | `"Sign in to access your dashboard"` |
| `#loading-state` | `fa-circle-notch` spinner + `"Loading authentication..."` — visible until Clerk initializes |
| `#clerk-sign-in` | Clerk `SignIn` component mounted here |
| `.auth-footer` | `"Powered by"` + link to `https://clerk.com` |

### Clerk SignIn Component Styling

Clerk's embedded component is customized with:
- Background: transparent (inherits white card)
- Primary color: `#6366f1` (indigo)
- Input background: `#f8fafc`
- Input border: `1.5px solid #e2e8f0`
- Submit button: gradient `#6366f1` → `#7c3aed`
- Header title / subtitle: hidden (replaced by custom `.auth-header`)
- After sign-in redirect: `/`
- Sign-up link redirects to: `/auth/signup`

---

## 6. Screen: Sign Up (`/auth/signup`)

**File**: `ui_client/templates/signup.html`  
**Style**: `ui_client/static/css/style.css` + inline styles

Identical layout and structure to Login screen with the following differences:

| Element | Different Value |
|---|---|
| Page `<title>` | `"Sign Up - LeadPilot"` |
| `.auth-subtitle` | `"Create your account to get started"` |
| Clerk component | `SignUp` (instead of `SignIn`) mounted in `#clerk-sign-up` |
| After sign-up redirect | `/` |

---

## 7. Screen: Error Page

**File**: `ui_client/templates/error.html`  
**Style**: `ui_client/static/css/style.css` + inline styles  
**Title**: `"Error - SalesShortcut"` *(legacy name)*

### Layout

```
[.error-container]
  └── [.error-card]
        ├── [.error-header]   ← Gradient red header with icon + title
        └── [.error-body]     ← Message + code block + action buttons
```

### Elements

| Element | Content |
|---|---|
| `.error-header` | Gradient background `#danger-color` → `#dc2626` |
| `.error-icon` | Large icon (4rem), rendered per error type |
| `.error-title` | Error heading text |
| `.error-subtitle` | Short error description |
| `.error-message` | Monospace code block with left red border — technical error details |
| `.action-button.primary` | **"Go Home"** or equivalent primary CTA → `/` |
| `.action-button.secondary` | Secondary action (e.g. back, retry) |

---

## 8. Screen: Architecture Diagram (`/architecture_diagram`)

**File**: `ui_client/templates/architecture_diagram.html`  
**URL**: Opens in new tab from landing page "View Architecture" button.

Displays a visual diagram of the multi-agent AI system architecture showing component relationships between Lead Finder, SDR Agent, Lead Manager, Calendar Agent, and backend services.

---

## 9. Modals & Overlays

All modals follow the same pattern: `.modal-overlay.hidden` (full-screen backdrop) containing `.modal-dialog`. Clicking the backdrop closes the modal. `event.stopPropagation()` on the dialog prevents accidental close.

---

### 9.1 AI Business Research Modal

**Trigger**: Click any business card in the Lead Finder column  
**Overlay ID**: `#research-dialog-overlay`  
**Close**: `closeResearchDialog()`

#### Modal Header (`.research-modal-header`)

| Element | Content |
|---|---|
| `.research-icon-badge` | `fa-brain` icon |
| `h3` | **"AI Business Research"** |
| `.research-subtitle` | `"Powered by intelligent analysis"` |
| `.modal-close` button | `fa-times` icon — closes modal |

#### Modal States

**Loading state** (`#research-loading`):
- Spinner animation
- Text: `"Analyzing business with AI..."` (animated dots)
- Subtext: `"Gathering insights and recommendations"`

**Results state** (`#research-results`):

Two-column grid layout:

**Left Column:**
| Section | Icon | Content |
|---|---|---|
| Business Overview | `fa-briefcase` | AI-generated description + `#research-industry` tag |
| Target Customers | `fa-users` | AI-generated customer profile text |
| Services & Products | `fa-concierge-bell` | Bulleted list `#research-services` |

**Right Column:**
| Section | Icon | Content |
|---|---|---|
| Online Presence | `fa-globe` | Website/social analysis `#research-online-presence` |
| Pain Points | `fa-exclamation-triangle` (warning) | Bulleted list `#research-pain-points` |
| Website Benefits | `fa-check-circle` (success) | Bulleted list `#research-benefits` |

**Full-width sections below grid:**
| Section | Icon | ID |
|---|---|---|
| AI Recommendation | `fa-lightbulb` (accent) | `#research-recommendation` — styled `.recommendation-box` |
| Conversation Starters | `fa-comments` | `#research-conversation-starters` — bulleted list |

**Error state** (`#research-error`):
- `fa-exclamation-circle` icon
- Heading: **"Analysis Failed"**
- Error message: `#research-error-message`
- Button: **"Close"** (`.btn-secondary`)

#### Modal Footer Actions

| Button | Style | Action |
|---|---|---|
| **Close** (`fa-times`) | `.btn-secondary` | `closeResearchDialog()` |
| **SDR Complete** (`fa-check`) | `.btn-primary.btn-sdr` | `sendToSdrDirect()` — marks business as SDR-processed |

---

### 9.2 SDR Dialog (Legacy)

**Overlay ID**: `#sdr-dialog-overlay`  
**Status**: Kept for backwards compatibility, not primary flow

#### Header
`fa-user-tie` + **"Send to SDR Agent"** + `fa-times` close button

#### Body
- Business preview (`#business-preview`) — populated by JS
- Description text: `"Do you want to send this lead to the SDR agent for engagement and qualification?"`
- Sub-label: **"The SDR agent will:"**
- Bullet list:
  - `"Contact the business via phone or email"`
  - `"Qualify the lead based on your criteria"`
  - `"Update you on the engagement status"`

#### Phone Input Section
| Element | Content |
|---|---|
| Label | **"Phone Number"** + `*` required mark |
| Description | `"Enter the phone number where you want to be reached for the call. This will override the business's phone number for outreach."` |
| `#sdr-phone-input` | `type="tel"`, placeholder: `"(555) 123-4567"` |
| `#phone-validation-icon` | Real-time validation icon (shows ✓ or ✗) |
| `#phone-validation-status` | Validation message text |

#### Footer
| Button | Style | State |
|---|---|---|
| **"Enter Phone Number"** / **"Send to SDR"** (`fa-paper-plane`) | `.btn-primary` | Disabled until valid phone entered; label updates on validation |

---

### 9.3 Human Input / Google IDX Modal

**Trigger**: System fires `human_input_required` WebSocket event  
**Overlay ID**: `#human-input-dialog-overlay`  
**Close**: `closeHumanInputDialog()`

#### Header
`fa-globe` + **"Automated Website Creation via Google IDX"** + `fa-times` close button

#### Auto-Creation Info Section
| Element | Content |
|---|---|
| `fa-magic` icon | Decorative info icon |
| `.info-title` | **"Our AI is creating a custom website automatically!"** |
| `.info-description` | `"The SDR agent has generated a tailored website prompt and is submitting it to Google IDX for automatic website creation."` |

#### Prompt Container
| Element | Content |
|---|---|
| Label | `fa-code` + **"Website Creation Prompt:"** |
| Copy button | `fa-copy` + **"Copy"** — calls `copyPromptToClipboard()` |
| `#human-input-prompt` | Read-only `<textarea>` displaying the generated website prompt |

#### Redirect Section
| Element | Content |
|---|---|
| Info text | `fa-info-circle` + `"Want to see the website being created? Open Google IDX with this prompt:"` |
| `.btn-redirect` | `fa-external-link-alt` + **"Open in Google IDX"** — calls `openFirebaseStudio()` |

#### Footer Actions

| Element | Content | Action |
|---|---|---|
| `.btn-secondary` | `fa-times` + **"Cancel Process"** | `closeHumanInputDialog()` |
| `#website-url-input` | `type="url"`, placeholder: `"Or manually enter website URL..."` | URL text input |
| `#submit-website-url-btn` | `fa-check` + **"Submit URL"** | `submitWebsiteUrl()` → `POST /api/human-input/{id}` |

---

### 9.4 Loading Overlay

**ID**: `#loading-overlay` (hidden by default, shown during long operations)

| Element | Content |
|---|---|
| `.spinner` | CSS animated spinner |
| `h3` | **"Processing leads..."** |
| `p` | `"Our AI agents are working hard to find and qualify your prospects."` |

---

## 10. Shared Components

### Animated Particles Background

Present on **all pages**. Eight `<div class="particle">` elements positioned randomly via JavaScript with randomized animation durations (10–30s) and delays (0–5s).

### Clerk Authentication

Integrated on all pages via the Clerk JS SDK:
```
https://deciding-reptile-45.clerk.accounts.dev/npm/@clerk/clerk-js@5/dist/clerk.browser.js
```

**Publishable key**: `pk_test_ZGVjaWRpbmctcmVwdGlsZS00NS5jbGVyay5hY2NvdW50cy5kZXYk`

**User Menu (when signed in)** — appears in header on both landing page and dashboard:

| Element | Content |
|---|---|
| `.user-avatar` | User profile photo or initials (first letter of name) |
| `.user-btn` label | First name or email prefix |
| `fa-chevron-down` | Dropdown indicator |
| **Dropdown — User info** | Full name + email address (display only) |
| **Dropdown — Manage Account** | `fa-user-cog` — opens Clerk account management modal |
| **Dropdown — Sign Out** | `fa-sign-out-alt` — red text — calls `Clerk.signOut()` → `/` |

Dropdown is dismissed by clicking anywhere outside `.user-menu`.

### Status Indicator Dots

Used in multiple places:

| CSS class | Color | Meaning |
|---|---|---|
| `.status-light.active` / `.status-indicator.active` | Green (`#22c55e`) | Agent/system running |
| `.status-light.idle` / `.status-indicator.idle` | Gray (`#94a3b8`) | Agent/system idle |
| `.status-light.error` | Red | Error state |

### Status Badges (on business cards)

| CSS class | Color | Label |
|---|---|---|
| `.status-found` | Blue | Found |
| `.status-contacted` | Gray | Contacted |
| `.status-engaged` | Green | Engaged |
| `.status-not-interested` | Red | Not Interested |
| `.status-no-response` | Yellow | No Response |
| `.status-converting` | Orange | Converting |
| `.status-meeting-scheduled` | Green (darker) | Meeting Scheduled |

### Button Styles

| Class | Appearance | Usage |
|---|---|---|
| `.btn-primary` | Solid blue `#2563eb`, white text | Confirm / submit actions |
| `.btn-secondary` | Outline / light gray | Cancel / close actions |
| `.btn-primary.btn-sdr` | Blue with check icon | SDR Complete action in research modal |
| `.reset-btn` | White outline | "New Search" in dashboard header |
| `.auth-btn` | Outlined primary | Login / Sign Up button (guest state) |
| `.run-button` | Large gradient blue | "Launch AI Agents" on landing page |
| `.btn-redirect` | Blue filled | "Open in Google IDX" |

### Font Icons

All icons use **Font Awesome 6.0.0** (`fa-*` classes, loaded via cdnjs CDN).  
Common icons used across the app:

| Icon | Used for |
|---|---|
| `fa-rocket` | Logo |
| `fa-search` | Lead Finder agent |
| `fa-user-tie` | SDR Agent |
| `fa-chart-line` | Lead Manager |
| `fa-calendar-alt` | Calendar / meetings |
| `fa-map-marker-alt` | City / location |
| `fa-phone` | Phone number |
| `fa-envelope` | Email |
| `fa-brain` | AI research |
| `fa-fire` | Hot lead |
| `fa-handshake` | Meeting scheduled |
| `fa-history` | Activity log |
| `fa-times` | Close / cancel |
| `fa-check` | Confirm |
| `fa-refresh` | Reload / reset |
| `fa-spinner fa-spin` | Loading state |
| `fa-external-link-alt` | Opens in new tab |
| `fa-copy` | Copy to clipboard |
| `fa-globe` | Website / web |
| `fa-arrow-left` | Back navigation |

---

*Last updated: February 28, 2026*
