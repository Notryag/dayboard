# UI Design Baseline

## Goal

Dayboard is a voice-first scheduling workspace with two equal product surfaces: conversation and the
day view. It must remain efficient on a phone while using desktop space as a real work area rather
than rendering a phone-shaped demo in the center of the viewport.

Visual decisions must not be scattered through components. Colors, spacing, radius, shadows,
typography, control sizes, and motion belong in global semantic tokens. Geometry owned by one
component belongs in custom properties on that component root.

## Responsive App Shell

The current application shell is:

```text
mobile (< 900px)
  -> transparent full-width overlay header with a floating circular view switch
  -> centered Dayboard wordmark without a container
  -> one active full-width view
  -> horizontal content swipe between conversation and schedule
  -> conversation is the default home view
  -> centered voice composer inside the bottom safe area

desktop (>= 900px)
  -> full-height, full-width two-pane work surface
  -> the same transparent shared header
  -> conversation pane on the left
  -> persistent day-view pane on the right
```

The desktop layout is a two-pane operational tool, not a dashboard of cards. On mobile, conversation
is the home page and the floating header control switches between the two top-level sections. Tasks remain
inside Schedule. The global header's right control opens a settings drawer for account information,
timezone, appearance, logout, and future settings. Appearance supports system, light, and dark themes.
The centered wordmark uses a restrained animated gradient glow behind the text.
The global header overlays the conversation scroller and remains visible while Conversation or Schedule
content scrolls. Its transparent treatment preserves the full-screen surface without introducing a
separate header band.
The root document, app shell, and full-screen page use the same surface background so notch, status-bar,
home-indicator, and overscroll areas do not reveal a second canvas color.

Mobile view switching uses a Motion-driven draggable track. The surface follows horizontal input
one-to-one, then combines travel distance and release velocity to choose a destination and settles
with an interruptible, non-bouncy spring. A left drag in Conversation opens Schedule; a right drag
in Schedule returns to Conversation. The gesture ignores the outer screen edges, interactive controls,
and horizontal scrollers such as the date rail so it does not compete with browser navigation or date
browsing. With reduced motion enabled, direct drag is disabled and the header control switches views
without spatial animation. Only the active mobile pane participates in focus and the accessibility
tree; both desktop panes remain available. The current app-like H5 shell locks the viewport to scale
`1` to prevent accidental pinch and focus zoom while navigating between these full-screen surfaces.

## Design Direction

Dayboard should feel:

- calm but recognizable
- precise
- modern
- personal
- work-focused
- voice-first

Avoid:

- marketing-style hero layouts
- decorative gradients as the main identity
- large dashboards before the core conversation works
- one-hue palettes where everything is blue, purple, beige, or dark slate
- hard-coded colors inside feature components

### 2026 Color Direction

The visual direction uses a cool system-neutral canvas with vivid semantic signals. Conversation
surfaces must read as cool white or neutral gray, never cream, beige, or warm yellow. The
implementation colors are screen-oriented product colors, not claimed digital equivalents of
proprietary forecast swatches.

| Semantic role | Light token value | Product use |
| --- | --- | --- |
| canvas | `#edf1f5` | viewport around the work surface |
| surface | `#f7f8fa` | primary application surface |
| brand / primary | `#087a72` | selected dates, voice idle, send, focus |
| AI / voice activity | `#d92d7a` | assistant mark, recording state, active progress |
| calendar | `#4967e8` | calendar entries and agenda markers |
| task | `#9a6700` | tasks and due-state markers |
| success | `#16845b` | completed and successful states |
| text | `#171b18` | primary readable content |

Strong colors should occupy a minority of the interface. Use them for state and hierarchy, not as
large decorative bands. Do not add gradients, decorative blobs, or arbitrary rainbow accents.

Color ownership is stable:

```text
teal     -> brand, selection, primary action, voice idle
fuchsia  -> AI identity and active voice processing
blue     -> calendar entries
amber    -> tasks and deadlines
mint     -> completion and success
red      -> errors and destructive/cancel states only
```

## Tokens

Use CSS variables as the first design-token layer. Map Dayboard's `--dayboard-color-*` product
tokens into shadcn theme variables so feature CSS Modules and shared UI primitives consume one
theme rather than parallel palettes.

Initial token groups include semantic colors, spacing, typography, control sizing, radii, focus,
opacity, shadows, and motion:

```css
:root {
  --color-bg: #edf1f5;
  --color-surface: #f7f8fa;
  --color-surface-raised: #ffffff;
  --color-surface-muted: #eef1f5;
  --color-text: #181a1d;
  --color-text-muted: #68717c;
  --color-border: #d9dfe7;

  --color-primary: #087a72;
  --color-primary-foreground: #ffffff;
  --color-primary-surface: #e2f3ef;
  --color-accent: #d92d7a;
  --color-calendar: #4967e8;
  --color-task: #9a6700;
  --color-success: #16845b;

  --message-user-bg: var(--color-primary);
  --message-user-text: #ffffff;
  --message-assistant-bg: #ffffff;
  --message-assistant-text: var(--color-text);

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;

  --font-size-caption: 12px;
  --font-size-label: 13px;
  --font-size-ui: 14px;
  --font-size-body: 15px;
  --font-size-title: 19px;
  --control-size: 44px;

  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 999px;

  --shadow-soft: 0 24px 70px rgb(26 57 45 / 11%);
}
```

These values are starting points, not brand law. Keep the names stable so later visual redesigns can change values without rewriting components.

Feature styles must not contain raw color values. Put theme-changing decisions in global semantic
tokens. Put geometry that belongs to one component, such as date-cell width or agenda time-column
width, in custom properties on that component's root. Structural CSS such as percentages, grid
fractions, and media-query conditions may remain literal when CSS variables cannot express them.

## Layout Rules

- Design mobile first, then expand carefully for desktop.
- The conversation screen should be usable at 360px width.
- Switch to the persistent two-pane workspace at 900px; do not squeeze two panes onto tablets.
- Use the full desktop viewport and give both panes independent scrolling.
- Keep the input dock fixed or sticky at the bottom.
- Keep the mobile composer inside the bottom safe area. Do not duplicate the Conversation/Schedule
  switch in a bottom tab bar while the header control owns that navigation.
- Respect all mobile safe-area insets. The viewport uses `viewport-fit=cover`; the floating header,
  scrollable content, composer, and drawers keep interactive content clear of notches and home indicators.
- Message bubbles should have stable max widths and must not shift layout while loading.
- Assistant messages use a raised neutral surface and subtle border. A long press opens a compact,
  WeChat-style action menu for real local actions only: copy and select text. Moving the pointer
  while pressing cancels the menu so vertical conversation scrolling remains natural.
- Use icons for microphone and send actions, with accessible labels.
- Render schedule results as individual timeline-style rows, not as cards nested inside a result
  card. Use a narrow calendar/task color rail, a small semantic icon surface, a clear title, and one
  restrained metadata line. Keep completion controls out of conversation results.
- Keep touch targets at least 44px.
- Avoid explanatory text in the product UI unless it is necessary for the current task.
- Do not wrap page sections in decorative cards. Borders divide work regions; shadows are reserved
  for the application shell, messages, dialogs, and primary controls.
- Use transitions only for color, opacity, and small transforms. Date selection and resource loading
  must not move fixed-format navigation controls.
- Gesture-driven navigation must track input directly, hand off release velocity, remain interruptible,
  and use a spatially symmetric return path. Use Motion for this interaction instead of CSS keyframes.
- Stagger multiple streamed schedule results by a few milliseconds so their arrival remains legible,
  but keep the full sequence brief and disable it under `prefers-reduced-motion`.

Voice is the conversation home's default input mode rather than a modal, page, or navigation item.
The primary voice control is a full-width hold-to-talk bar at the bottom, following the familiar
WeChat interaction shape without copying its visual branding. Recording feedback stays inside the
bar and the keyboard switch remains a compact icon on its right. Its stable states are:

```text
voice idle   -> neutral "hold to talk" bar, keyboard-mode icon on the right
requesting   -> bar shows microphone permission progress
recording    -> fuchsia bar with live level/timer, slide up to cancel, release to send
transcribing -> upload/provider progress and cancel before command submission
text         -> microphone-mode icon, editable text, send
```

Voice commands submit automatically after successful transcription; keyboard commands still require
an explicit send action. Preserve an existing draft by prepending it to the recognized voice command.
After a completed command, return to voice mode when voice is available. Release microphone tracks,
audio contexts, timers, and local blobs after stop, cancel, or unmount.

## Component Boundaries

Current split:

```text
app/page.tsx                         # route entry only

features/workspace/
  DayboardApp.tsx                    # authenticated workspace composition and navigation
  MobileViewPager.tsx                # measured Motion drag, velocity decision, and spring settling

features/chat/
  useConversationSession.ts          # thread, history, active Run, command, clarification, and undo flow
  ChatMessageList.tsx                # message rendering and clarification placement
  Composer.tsx                       # mode, capabilities, transcription, and errors
  VoiceComposer.tsx                  # hold/release/cancel gestures and recording feedback
  TextComposer.tsx                   # keyboard input, send, and mode switch

features/voice/
  useVoiceRecorder.ts                # MediaRecorder and browser media resource ownership
  api.ts                              # transcription HTTP boundary
```

Keep API calls out of visual components. `VoiceComposer` and `TextComposer` receive state and
callbacks only; provider calls stay in the composer coordinator through `features/voice/api`.

## State

For the first static screen, local React state is enough.

When the command flow becomes real:

- use TanStack Query for server-backed command/run state
- use local React state for composer text and transient recording state
- use Zustand or Jotai only when state needs to be shared across distant components

Agent run records, calendar entries, tasks, and transcripts should remain server-backed.

## Day View

The focused day view is now a first-level product surface: persistent on desktop and selected through
the mobile Schedule tab. It is not a month board or a dashboard. Keep these stable regions:

```text
day-view panel
  -> selected weekday / native month-year date picker
  -> horizontally scrollable date rail centered on the selected date
  -> chronological agenda merging calendar entries and dated tasks
  -> separate undated open-task list
```

The API must interpret a selected `YYYY-MM-DD` using the trusted scheduling timezone. The browser must
not invent UTC offsets for arbitrary IANA timezones. Date-only navigation can use calendar-day
arithmetic; event instants are formatted in the timezone returned by the account API. This is
currently server-configured `Asia/Shanghai`; a trusted tenant setting may replace it later.

The selected date uses the semantic selection background. Today uses a neutral surface when it is
not selected; do not use a decorative dot. The initial 31-day rail starts with today at the left edge
so upcoming dates receive the available space. Swiping scrolls the rail but does not change
selection; tapping a cell selects it. A distant date jump starts a new forward-looking window at that
date. The month-year control retains the native date picker for distant jumps.

Render the chronological agenda as separate cards. Place each start-time label in the vertical space
before its card instead of reserving a left-hand time column. Calendar cards show duration rather
than an end clock time; exact start and end times remain available in the bottom action sheet. Keep undated
task rows compact, wrap long titles, preserve 44px controls, and give each source independent loading,
error, retry, and pagination state. The date rail uses a 31-day window, CSS scroll snapping, and
cached `Intl.DateTimeFormat` instances; do not add a carousel or date-picker dependency for this
interaction.

Calendar entries and tasks share one schedule-item component across the day view and assistant
messages. It chooses a semantic Lucide icon from centralized title keywords; icons use semantic
foreground colors without decorative background tiles. Each active card has a separate right-aligned
circular completion control; the rest of the card opens a bottom action sheet instead of a centered
dialog. The sheet presents details and vertical edit, complete, and cancel actions, and editing
replaces the sheet body without opening another layer. Calendar editing covers title, start time,
and duration; task editing covers title and optional due time. Mutations use `updated_at` as an
optimistic-concurrency boundary.

The direct circular completion control appears only in schedule/day-view contexts. Assistant
confirmation cards reuse the same content and detail sheet but omit that control: a newly created
item should read as confirmation rather than immediately prompting completion.

Component ownership:

```text
SchedulePanel.tsx      # selected date and resource composition
ScheduleHeader.tsx     # weekday and native date picker
DateRail.tsx           # date window, selection, horizontal navigation
DayAgendaSection.tsx   # merged chronological calendar/task display
TaskListSection.tsx    # undated task display
ScheduleItem.tsx       # shared semantic-icon card, details, direct actions
ScheduleItemEditForm.tsx # direct editing and account-timezone conversion
useSchedulePage.ts     # TanStack Query pagination, cache, cancellation, retry
features/reminders     # unread badge, reminder drawer, source navigation, retry
date.ts                # cached display formatters and date-key arithmetic
```

Circular visualization, month/week layouts, and browser/PWA push delivery are later product slices.

## Interaction And Performance Acceptance

- Do not add carousel or date-picker dependencies for the current interactions. Native horizontal
  scrolling, native date input, CSS Grid, and TanStack Query server state are sufficient.
- Keep the 31-day rail window stable when a date is tapped. Recenter only after an explicit distant
  date jump or keyboard navigation beyond the current window.
- Cache date/time formatters and use tabular numerals for times and date cells.
- Keep message, date-cell, toolbar, and composer dimensions stable across loading and active states.
- Refresh the persistent day-view resources after a command completes and when mobile navigation
  returns to Schedule; replacing the old remounting dialog must not leave stale schedule data.
- Honor `prefers-reduced-motion`; no essential state may depend on animation.
- Validate at 390x844 and 1280x800. There must be no horizontal overflow, overlapping controls,
  blank panels, or page-level scrolling in place of pane scrolling.
- Verify text and icon contrast in both light and dark color schemes before release.
