---
name: mock-up
description: Use when the person asks for a mockup, wireframe, screen design or draft, screen flow, phone frame or UI draft, i.e. a UI mockup or prototype image as a self-contained HTML file plus a PNG capture — web/app screens, dashboards, wireframes, multi-screen flow boards, device-frame (phone/laptop) mockups, or a macOS-style document page or slide shown as content only (doc/slide types), optionally with dynamic effects (loading, count-up, hover feedback, transitions). Not for the Industry-style deliverable document (my-doc), a navigable slide deck (slide-decks) or architecture diagrams (archify).
argument-hint: "<description of the screen to make> [screen | wireframe | flow | device | doc | slide] [output file path]"
---

# mock-up

Make a UI mockup as a **single HTML file plus a PNG**. The style is chosen per request; when none is given, the Swift style is the default (mobile = iOS, web app = macOS window). This skill owns the output format, the save location, the capture and the check steps. Visual direction such as color and typography comes from the `frontend-design` skill.

Output constraints: one self-contained HTML file on a fixed canvas. Inline CSS, inline JS and CSS animation are allowed. No external scripts, fonts, images or CDN. Respect `prefers-reduced-motion` (with reduced motion, show the settled final state without movement).

## When not to use

Other skills, if installed:

- Scrolling documents, landing pages, one-pagers in the Industry blueprint style (the deliverable itself) → `my-doc`
- A navigable presentation deck (scroll-snap, keyboard, slide rail) → `slide-decks`
- A document page or slide in the macOS look as a static HTML + PNG → this skill, `doc` / `slide` type
- Architecture, sequence or state diagrams → `archify`
- Working app code → `frontend-design`

## Steps

1. **Pick the type** — Choose from the argument (`screen`/`wireframe`/`flow`/`device`/`doc`/`slide`) or from the request, and read the matching reference files. For a combination, read all of them (for example, a 3-screen flow inside phone frames = `flow.md` + `frames.md`).

   | Type | Files to read |
   |---|---|
   | `screen` app/web screen (default) | `templates/canvas.html`. When using the Swift default frames (mobile = iPhone, web app = macOS window) or another frame, also `references/frames.md` |
   | `wireframe` | `references/wireframe.md` |
   | `flow` multi-screen flow | `references/flow.md` (see `frames.md` for screen sizes) |
   | `device` device frame | `references/frames.md` |
   | `doc` document page, content only | `references/doc-slide.md`, then `examples/doc.html` and `examples/doc.png` |
   | `slide` slide(s), content only | `references/doc-slide.md`, then `examples/slide.html` and `examples/slide.png` |

   When adding dynamic effects, read `references/effects.md` for any type (step 4).

   If the type is ambiguous, treat it as `screen` and say in the report that you chose it.

2. **Decide the style** — Take the direction from the user's instructions (color, tone, style) and the product's character. Define the style as `:root` tokens.
   - `screen`/`device`:
     - No style given, mobile app → **iOS look**: iPhone frame, large title, grouped list, tab bar, SF font, system colors (the Phone frame and "iOS look" in `references/frames.md`).
     - No style given, web app → **macOS window look**: traffic-light buttons, toolbar, sidebar, SF font, system colors (the frame is "macOS window" in `references/frames.md`).
     - With no style given, the Swift default above is the direction. Calling `frontend-design` is optional then, and if it conflicts with the Swift default, the Swift default wins.
     - Exception: a style the user states (for example "material", or a specific brand color) always wins over this default. Then drop the Swift default and, if useful, take only the visual direction from `frontend-design`.
     - In every case, this skill's output constraints (single file, no external resources, fixed canvas) win.
   - `doc`/`slide`: the macOS content look in `references/doc-slide.md`. **No window frame**: no traffic lights, toolbar, sidebar, inspector or gradient backdrop; the canvas is the page or the slide. A style the user states still wins.
   - `wireframe`/`flow`: do not apply the Swift default. Do not call `frontend-design` either; follow `references/wireframe.md` (grayscale rules) and `references/flow.md` (flow board rules).

3. **Build** — When the argument gives an output file path (`…/index.html`), build there and put the PNG in the same folder. Otherwise save to `<cwd>/.my-mockup/<yymmdd>-<slug>/index.html` (the slug is English kebab-case; add `-2` if the folder exists; the `-2` rule applies only to this default folder). If the cwd is inside a skill folder (`~/dev/skills/...` or `~/.claude*/skills/...`), the default folder is `~/dev/.my-mockup/<yymmdd>-<slug>/` instead. Copy `templates/canvas.html` to `index.html` and fill it in.
   - Change `<meta name="mockup-size" content="WxH">` and `--w`/`--h` in `:root` **together**. The default is 1440x900 (desktop) and 390x844 (app screen). When using a frame, use the size given in `references/frames.md`; for `doc`/`slide`, the sizes in `references/doc-slide.md`.
   - Keep the capture boot script in the template `<head>` (the inline script that sets `data-capture`) and place it before any effect markup.
   - Use system fonts only (SF first). The resource rules are in "Output constraints" above.
   - Draw images with CSS/SVG or use flat-color placeholders.
   - Use realistic sample data (names, amounts, dates), not lorem ipsum.
   - Set `<html lang>` to the language of the content.

4. **Dynamic effects (optional)** — Add motion only when it helps.
   - Pick from `references/effects.md`: (a) loading and progress, (b) numbers and text, (c) interaction feedback (HTML only), (d) transitions and scroll.
   - Copy the snippets as they are. Each snippet has a settled branch under `html[data-capture]`. Do not remove it.
   - Put each effect's `<script>` on the page **once**. If you use the same effect in several places, repeat only the HTML (pasting the script again attaches the handler one more time). Do not remove the `dataset.fx` guard in the snippets either.
   - The PNG shows the **final state** after the motion ends (`capture.sh` opens the page with `?capture=1`). Intermediate frames are not captured. Interaction effects such as hover, ripple, tilt, flip and shuffle move only in the HTML; the PNG shows the rest state.

5. **Capture** — `sh <this skill folder>/scripts/capture.sh <folder>/index.html` → `index.png` (2x) in the same folder. This skill folder is the folder that holds this SKILL.md (in the my-agent plugin, `${CLAUDE_PLUGIN_ROOT}/skills/mock-up`). If the script exits with code 1 (no browser, capture failed), report the reason as it is and do not pretend a PNG exists.

6. **Check** — Open the PNG with Read and look for clipping, overflow, empty areas, overlap and font fallback. If you added effects, also check that numbers show their final values, that revealed elements are visible, and that progress bars and rings show their final values (zero or hidden means the settled branch is missing). A large canvas may look shrunk in the 2x PNG, so check details with `--scale 1`. If there is a problem, fix the HTML and repeat from step 5 (at most 3 times). Report any problem that remains after 3 rounds.

7. **Report** — The absolute paths of the HTML and the PNG, and one line on the chosen type and style (including whether the Swift default or a user-stated style was used). If effects were added, name them.

## Edit requests

When asked to change an existing mockup, edit `index.html` in the same folder and capture again. Do not create a new folder. If you are adding effects and that `index.html` was made before the boot script existed (no boot script in `<head>` that sets `data-capture`), first copy the capture boot script from `templates/canvas.html` into `<head>`, then add the effects. To keep the previous version, copy `index-v1.html` and `index-v1.png` together.

## Notes

- The default folder `.my-mockup/` is a hidden folder. When working in a git repository, leave the commit decision to the user and do not edit `.gitignore` on your own.
- To use a browser other than Chrome, set the `CHROME_BIN` environment variable.
- Opening an HTML file that has effects directly in a browser shows the motion. If "Reduce motion" is on in macOS settings, only the final state shows and nothing moves.
