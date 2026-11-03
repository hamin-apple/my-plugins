# doc and slide types (macOS content look)

These types show a document or a slide in the macOS look, **with the content only**. Do not draw a window frame, traffic lights, toolbar, sidebar, inspector, slide navigator, or a gradient presentation backdrop behind it. The canvas *is* the page or the slide.

**Read the matching example first** and match its level of finish: `examples/doc.html` (+ `doc.png`) and `examples/slide.html` (+ `slide.png`). Reuse their CSS (copy the rules, then change the content). The examples are the quality bar, not a template you must copy section for section.

## Sizes

| Type | Canvas (`mockup-size` and `--w`/`--h`, change together) |
|---|---|
| `doc` | width 1440; height fits the content. Build with a tall height (for example 2400), capture with `--scale 1`, read where the footer ends, then set the height to that point (no empty band below the footer, no clipping) and capture again at 2x. |
| `slide`, one slide | 1280x720 |
| `slide`, several slides | Stacked board: canvas width 1360, each slide 1280x720 with `border-radius: 12px` and `box-shadow: 0 0 0 .5px rgba(0,0,0,.12), 0 8px 24px rgba(0,0,0,.08)`, 40px gap and 40px outer padding, board background `#e5e5ea`. Height = N × 720 + (N + 1) × 40. Maximum 6 slides per file; split into `index.html`, `index-2.html` … beyond that. |

## Tokens

Start from `templates/canvas.html` tokens (SF font, Apple system colors). Page background is white (`#fff`); `--bg` (`#f2f2f7`) is for grouped-list backgrounds; cards use `#f5f5f7`.

## Look (what makes the examples work)

- **Display type**: SF bold, tight tracking. doc hero 64–72px, `letter-spacing: -.04em`, `line-height: 1.03`; section titles 36px `-.03em`; slide title 54px `-.035em`. Never uppercase display text (that is the Industry look of `my-doc`).
- **Eyebrow** above titles: 14–16px, weight 600, `--accent`. On slides it is uppercase with `.06em` tracking.
- **Key figures** = inset grouped list (doc) or stat tiles (slide), never a bordered table. Values 28px (doc) / 44px (slide), weight 600–700, `font-variant-numeric: tabular-nums`. A change badge is a green tinted pill (`rgba(52,199,89,.15)` background, `#1f9d41` text).
- **Cards**: filled `#f5f5f7`, `border-radius: 18px` (doc) / `20px` (slide), no border. A colored icon tile (44px, radius 11px, system color) goes on top. Icon tiles and swatches drawn with `<i>` need `display: block`, or they collapse to nothing outside a flex row.
- **Buttons**: pills. Filled `--accent` for the primary, tinted (`color-mix(in srgb, var(--accent) 12%, transparent)`) for the secondary.
- **Charts**: CSS bars, `border-radius: 10px 10px 3px 3px`, light tint for the comparison period and accent gradient for the focus period, value labels above, legend below the chart title.
- **One strong color surface** per doc at most (the closing CTA card with an accent → indigo gradient). Everything else is white or light gray.
- **Cards that fill a tall row** are `display: flex; flex-direction: column`, with the key value or footer line pushed down by `margin-top: auto`, so the card does not end in an empty half.
- **Korean content**: `<html lang="ko">` and `word-break: keep-all` on `body`, or words break mid-syllable (청/구서). Negative tracking stays as is.
- **Hairlines**: `.5px solid var(--separator)` for nav, footer, list separators.

## doc section grammar

Same section order as `my-doc`, restyled: nav → hero (copy left, key-figures grouped list right) → features (3 cards) → split (CSS-drawn visual + copy) → quote + close side by side → footer. Each section is optional; drop it rather than fill it with filler.

## slide grammar

Eyebrow → title (one line if it fits; `white-space: nowrap` only when you checked it fits) → body grid (stat tiles left, chart or cards right) → small footer line (deck name left, `n / N` right). The body grid must fill the slide down to about 56px from the bottom edge; no empty lower third.

## Content rules

- No content given by the user → realistic sample data (names, amounts, dates), as for every mock-up type.
- Content given by the user → use it as given. Do not invent figures, quotes or facts to fill a section; leave unknown values as `[PRICE]`-style bracket placeholders, or drop the section (the `my-doc` rule).

## Check (in addition to SKILL.md step 6)

- No window chrome anywhere in the PNG.
- No empty band at the bottom of a doc, no empty lower third on a slide.
- Every icon tile and swatch is visible.
- Titles did not wrap into an orphan word (one word alone on the last line); shorten or resize.
