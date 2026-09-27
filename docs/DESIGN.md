# Design system: the agent screen

The agent screen (`static/agent.html`, `agent.css`, `agent.js`) is a review desk for a bank or company
onboarding a customer. The visual language is **Swiss-style minimalism** plus an **accessible, ethical**
style, as used for traditional finance.

It has to feel calm and trustworthy, show its evidence, and make the hand-over to a person obvious. It runs
offline, so it uses system fonts and inline SVG icons, with no external fonts, CDNs or icon libraries.

## Principles

1. **Proof before promises.** The first screen shows the live held-out results (`/api/evaluation`), not
   marketing copy.
2. **Status is never colour alone.** Every state has an icon and a word: accepted (check), to a person
   (person with a check), blank (dash), blocked (warning triangle).
3. **One action colour.** Teal is only for actions and the brand. Green, amber and red only mean status.
4. **The decision is computed live.** Demo cards say what was planted in a file. They never promise an
   outcome.
5. **Two languages, one layout.** Every component uses logical properties (`inset-inline-*`,
   `margin-inline-*`), so Arabic mirrors correctly, including the arrows.

## Tokens (`:root` in `agent.css`)

| Token | Value | Use |
|---|---|---|
| `--ink` | `#0f1f2e` | Text (navy ink) |
| `--muted` | `#556575` | Secondary text (≥ 4.5:1 on white) |
| `--brand` / `--brand-ink` | `#11685d` / `#0a4c44` | Actions, brand, focus ring base |
| `--good` · `--warn` · `--bad` · `--info` | `#157f4c` · `#955300` · `#b42318` · `#1d5fa6` | Status only, each with a tint |
| `--r-sm` · `--r` · `--r-lg` | 8 · 12 · 16 px | Radius scale |
| `--shadow-1` · `--shadow-2` | subtle · raised | Resting cards · hover and verdict |
| `--t-fast` · `--t` · `--ease` | 150 ms · 220 ms · `cubic-bezier(.2,.7,.2,1)` | Motion |

**Type.** Segoe UI Variable, with Noto Sans Arabic as the Arabic fallback. Body text is 15 px, lead text
16 px, the headline 30–34 px, and nothing is smaller than 11 px. Numbers use `tabular-nums`, and Arabic
gets a taller line height (1.75).

## Components

- **Proof strip.** Four held-out metrics with icons, plus a link to the full evaluation.
- **Scenario gallery.** A featured "all documents in one photo" card and six scripted stories
  (`DEMO_PLAN`). Each card has a "planted" chip.
- **Agent timeline.** Numbered steps turn into checkmarks. Next to them are the elapsed time and the
  documents as they are found.
- **Verdict.** An SVG icon and a composition bar (accepted / to a person / blank). The legend doubles as the
  statistics.
- **Document rail.** Sticky jump links, one per document, each with its own status.
- **Field row.** Label, value, confidence meter with a threshold mark, and a status chip with an icon.

## Accessibility and quality checks

- Visible focus ring on everything (`:focus-visible`, 3 px). Real `<button>`s for every action, including
  the reasons list. `aria-current` on the active tab and the current step.
- Touch targets are 40–44 px. There is no horizontal scroll at 375 px (checked).
- `prefers-reduced-motion` turns off every animation and transition.
- The guided tour's selectors (`static/tour.js`) are part of the contract. Keep `#dropzone`,
  `.demo-card.tone-info`, `#decision .stats`, `.controls`, `#reasonsPanel`, `.doc-card .field` and `.actions`.
