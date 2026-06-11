# Silicon-Inspired Desktop UI Design

## Objective

Redesign the complete `qidian_save` desktop client as a cohesive, polished dark
desktop application inspired by SiliconUI, while retaining the current PyQt6,
PyQt6-Fluent-Widgets, business logic, API contracts, and threading model.

The selected direction is a balanced utility interface: SiliconUI's purple-black
depth, rounded surfaces, and restrained artistic character combined with dense,
clear tables and explicit actions suitable for backup and decryption workflows.

## Scope

The redesign covers:

- Login dialog
- Main `FluentWindow`, navigation, title area, and status area
- Search panel
- Qidian QR login panel
- Bookshelf panel
- Book detail panel
- Backup task panel
- `.qd` decryption panel
- Usage panel
- Reader widget
- Dialogs, tables, trees, forms, loading states, empty states, and feedback

The application will support one production theme only: dark.

## Non-Goals

- No migration to PyQt5 or SiliconUI
- No SiliconUI runtime dependency
- No server or API changes
- No changes to backup, authentication, decryption, ADB, or cookie behavior
- No broad backend refactoring
- No new light theme implementation

## Architecture

### Design System

`desktop/theme.py` remains the source of truth for semantic colors, typography,
spacing, radii, and component dimensions. Tokens will describe roles rather than
individual screens:

- Canvas and navigation backgrounds
- Elevated and inset surfaces
- Borders, dividers, and focus rings
- Primary, secondary, muted, and disabled text
- Purple and magenta brand accents
- Success, warning, danger, and information colors
- Compact, regular, and large control heights

`desktop/style/dark.qss` consumes the same semantic intent and owns visual states
for standard Qt and Fluent widgets.

### Shared Components

A small shared component module will provide reusable structure without replacing
Qt primitives:

- `PageHeader`: eyebrow, title, subtitle, and optional actions
- `SurfaceCard`: standard rounded content surface
- `StatCard`: label, value, optional accent and supporting text
- `EmptyState`: concise message and recovery action
- Layout helpers for page margins and section spacing

Components expose object names and dynamic properties so appearance remains in
global QSS. They do not contain business logic.

### Main Shell

The application keeps `FluentWindow` and its navigation system. The shell will use:

- Compact icon navigation with a strong selected state
- A restrained branded title area
- Purple-black canvas with clearly separated content surfaces
- A compact bottom account and usage status area
- Consistent content margins across every route

Book detail remains a programmatic route rather than a persistent navigation item.

## Visual Language

### Color

- Main canvas: deep purple-black
- Navigation: slightly darker than the canvas
- Standard cards: raised plum-charcoal surface
- Inputs and data regions: darker inset surface
- Primary accent: muted purple
- Highlight accent: soft magenta
- Borders: low-contrast lavender-gray
- Text: warm white with distinct secondary and tertiary levels

Gradients are limited to high-value elements such as progress fills and selected
indicators. Large decorative gradients are excluded from data-heavy screens.

### Typography

The application uses the best available system sans-serif stack with Microsoft
YaHei UI for Chinese fallback. Hierarchy:

- Page title: 24 px equivalent, semibold/bold
- Section title: 16-18 px equivalent, semibold
- Body and controls: 13-14 px equivalent
- Caption and metadata: 11-12 px equivalent
- Numeric metrics: tabular appearance where supported

### Shape and Spacing

- Standard radius: 10 px
- Large card radius: 14 px
- Compact radius: 7 px
- Page gutter: 24-28 px
- Section spacing: 16 px
- Internal card padding: 16-20 px
- Controls remain compact enough for desktop data workflows

## Panel Design

### Login

Centered authentication card with clear product identity, concise explanation,
one primary action, and subdued technical status. Authentication behavior remains
unchanged.

### Search

Page header, compact search card, results summary, and a dense results table.
The detail action uses the theme accent instead of a hardcoded blue.

### QR Login

Two-column or stacked card layout depending on available width: QR code and
instructions/status. Loading, expiration, success, and retry states are visually
distinct.

### Bookshelf

Header and refresh action above a dense table. Empty and authentication-required
states provide direct recovery guidance.

### Book Detail

Book identity and actions appear in a top summary card. Catalog and purchased
chapter data use consistent tabs, tables, or grouped surfaces. Backup remains the
single primary action.

### Backup

Task summary metrics, progress, current activity, chapter results, and downloads
are visually separated. Destructive cleanup stays subordinate and clearly marked.

### Decryption

The existing workflow is reorganized into:

1. Device and acquisition toolbar
2. Book/chapter tree as the main workspace
3. Collapsible or compact parameter area
4. Primary decryption and merge actions
5. Log output as an inset technical surface

All existing controls and behavior remain available.

### Usage

A focused usage card with progress, three metric cards, reset information, and
refresh action. Inline hardcoded light styles are removed.

### Reader

Reading content gets a low-glare surface, readable line spacing, restrained chrome,
and consistent controls. Content readability takes priority over decorative effects.

## Interaction States

Every interactive control must have distinct default, hover, pressed, focused,
disabled, and busy states. Async actions disable duplicate submission and expose
visible progress or status text. Error messages include a recovery path where one
exists.

Tables and trees support clear hover and selected states without relying only on
color. Keyboard focus remains visible.

## Implementation Constraints

- UI changes from worker threads continue through signals or main-thread callbacks.
- Panel code must not set colors for buttons, inputs, tables, or standard text.
- Inline styles are permitted only for genuinely dynamic visual data that cannot be
  represented by a semantic property.
- Existing user changes in the dirty worktree must be preserved and incorporated.
- No client/server coordination document is needed because API behavior is unchanged.

## Testing and Verification

Verification includes:

- Static scan for remaining hardcoded light colors and inappropriate inline styles
- Import and compile checks
- Existing test suite, if present
- Focused tests for theme loading and shared component construction
- Offscreen construction of the login dialog, main window, panels, and reader where
  dependencies permit
- Actual application launch with a controlled local/mock path when practical
- Screenshot-based visual inspection of representative screens
- Confirmation that navigation and core callbacks remain connected

## Acceptance Criteria

- All desktop surfaces share one coherent dark Silicon-inspired visual system.
- No panel appears as a light-theme remnant.
- Search, bookshelf, backup, and decryption remain information-dense and usable.
- Primary actions are visually obvious and destructive actions are separated.
- Existing business behavior and API contracts are unchanged.
- The application starts successfully and key panels construct without exceptions.
- No unrelated files or server repository code are modified.
