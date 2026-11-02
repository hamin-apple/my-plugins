# Dynamic effects

A collection of copy-paste snippets that add motion to a mockup HTML. The techniques come from an HTML dynamic-effects demo, adapted to the Swift tokens (system colors, SF font) and the capture contract. All colors use the `:root` tokens of `templates/canvas.html` (`--accent`, `--separator`, `--fill`, `--secondary-label`, and so on). The snippets break without the tokens, so start from canvas.html.

## Rules

- **One file**: the output constraints in `SKILL.md` apply (inline CSS and JS only, no external resources). Do not use confetti or particle libraries.
- **Settled state**: the PNG captures the final state after the motion ends. When `capture.sh` opens the page with `?capture=1`, the boot script in canvas.html sets `data-capture` on `<html>`. A viewer with reduced motion on (`prefers-reduced-motion: reduce`) gets the same attribute and sees the same final state. Other viewers see the motion.
  - CSS snippets: the rules under `html[data-capture]` give the final state (`animation: none`, final opacity and transform, stop on a representative frame).
  - JS snippets: check `document.documentElement.hasAttribute('data-capture')` and go straight to the final state without animating.
- **Copy snippets as they are.** When you adapt one, do not remove the settled branch. Change the final numbers, text and values through `data-*` attributes or CSS variables.
- **Self-contained JS**: wrap every JS snippet in `(() => { … })();` and create no top-level `const`/`let`/`function`/`class` names. Find elements by class or data attribute, not by id. Then several snippets can share a page with no redeclaration errors.
- **One script per page**: when you use the same effect in several places, repeat only the HTML and put the `<script>` once (pasting the script again attaches the handler one more time). Each snippet has the guard `if (el.dataset.fx) return; el.dataset.fx = 1;`, so even if it is pasted twice by mistake it runs once per element. Do not remove the guard.
- **typing and scramble markup**: put the final text in the markup. A normal viewer may see the final text for one frame at the start. This flash is accepted.
- Prefix CSS `@keyframes` names with `fx-` (avoids clashes with page CSS).
- The JS snippets in this file put the `<script>` at the end of `<body>` (the elements must exist first).
- Do not add many infinite loops (spinner, shimmer, pulse, gradient) at once. Use one or two per screen so the eye is not split.

## Settled final-state table (PNG, reduced motion)

| Effect | In the PNG and with reduced motion | How to build it |
|---|---|---|
| count-up (JS, `@property`) | final number | JS: final value in `textContent`. CSS: `--n: var(--to)` under `html[data-capture]` |
| typing, scramble | full text | JS: full text in `textContent`, caret hidden |
| reveal (entrance fade) | visible, no offset | `opacity: 1; transform: none; transition: none` under `html[data-capture]` |
| spinner (and other infinite loops such as dots and pulse, the same way) | stopped on one representative frame | `animation: none` + a fixed `transform` |
| skeleton shimmer | highlight position fixed | `animation: none` |
| gradient text | gradient position fixed | `animation: none` |
| progress bar, ring | final value | `animation: none` (the element's base width or dashoffset is the final value) |
| scroll-driven bar, entering box | final value (visible) | `animation: none`; the bar uses `scaleX(var(--settled, 1))` |
| hover/press, ripple, 3D tilt, card flip, View Transitions shuffle | still (rest) state | HTML only: the PNG has no motion. With reduced motion, ripple and tilt attach no listener, hover/press has its transition turned off, flip stays still without rotating, and shuffle reorders without a transition |

HTML-only effects (hover/press, ripple, tilt, flip, shuffle) move only with interaction. The PNG captures only the rest state, so design that state to look good.

## (a) Loading and progress: spinner, skeleton shimmer, progress bar, progress ring

### spinner

```html
<div class="fx-spinner"></div>
```

```css
.fx-spinner { width: 28px; height: 28px; border-radius: 50%;
  border: 3px solid var(--separator); border-top-color: var(--accent);
  animation: fx-spin .8s linear infinite; }
@keyframes fx-spin { to { transform: rotate(360deg); } }
html[data-capture] .fx-spinner { animation: none; transform: rotate(45deg); }
```

### skeleton shimmer

```html
<div class="fx-skel"><i class="fx-skel-av"></i><div class="fx-skel-lines"><i></i><i></i><i></i></div></div>
```

```css
.fx-skel { display: flex; gap: 12px; align-items: center; width: 100%; }
.fx-skel i { display: block;
  background: linear-gradient(90deg, var(--fill) 25%, rgba(120,120,128,.04) 50%, var(--fill) 75%);
  background-size: 200% 100%; animation: fx-shimmer 1.4s linear infinite; border-radius: 6px; }
.fx-skel-av { width: 48px; height: 48px; border-radius: 50% !important; flex: none; }
.fx-skel-lines { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.fx-skel-lines i { height: 12px; }
.fx-skel-lines i:last-child { width: 60%; }
@keyframes fx-shimmer { to { background-position: -200% 0; } }
html[data-capture] .fx-skel i { animation: none; }
```

### progress bar

Set the value with `--v` (the fill width). The bar fills up to `--v`, and the PNG ends at that width.

```html
<div class="fx-bar" style="--v: 72%"><i></i></div>
```

```css
.fx-bar { width: 100%; height: 8px; border-radius: 99px; background: var(--fill); overflow: hidden; }
.fx-bar i { display: block; height: 100%; width: var(--v, 70%); border-radius: 99px; background: var(--accent);
  transform-origin: left; animation: fx-fill 1.2s cubic-bezier(.2, .8, .2, 1) both; }
@keyframes fx-fill { from { transform: scaleX(0); } }
html[data-capture] .fx-bar i { animation: none; }
```

### progress ring

The SVG circle has `pathLength="100"`, so `--v` is a number from 0 to 100.

```html
<svg class="fx-ring" style="--v: 68" width="96" height="96" viewBox="0 0 96 96">
  <circle class="fx-ring-bg" cx="48" cy="48" r="40" pathLength="100"/>
  <circle class="fx-ring-fg" cx="48" cy="48" r="40" pathLength="100"/>
</svg>
```

```css
.fx-ring circle { fill: none; stroke-width: 8; }
.fx-ring-bg { stroke: var(--fill); }
.fx-ring-fg { stroke: var(--accent); stroke-linecap: round; stroke-dasharray: 100;
  stroke-dashoffset: calc(100 - var(--v, 70)); transform: rotate(-90deg); transform-origin: 48px 48px;
  animation: fx-ring 1.4s cubic-bezier(.2, .8, .2, 1) both; }
@keyframes fx-ring { from { stroke-dashoffset: 100; } }
html[data-capture] .fx-ring-fg { animation: none; }
```

## (b) Numbers and text: count-up, typing, scramble, gradient text

### count-up (JS)

```html
<span class="fx-count" data-to="1240">0</span>
<script>
(() => {
  const settled = document.documentElement.hasAttribute('data-capture');
  document.querySelectorAll('.fx-count').forEach(el => {
    if (el.dataset.fx) return; el.dataset.fx = 1;
    const to = +el.dataset.to;
    if (settled) { el.textContent = to.toLocaleString(); return; }   // PNG, reduced motion: final number
    const t0 = performance.now(), dur = 1200;
    requestAnimationFrame(function tick(t) {
      const p = Math.min(1, (t - t0) / dur);
      el.textContent = Math.round(to * (1 - Math.pow(1 - p, 3))).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    });
  });
})();
</script>
```

Add `.fx-count { font-variant-numeric: tabular-nums; }` to the page CSS so the number width does not jitter.

### count-up (CSS `@property`, no script needed)

Integers only. The final value is `--to`.

```html
<span class="fx-count-css" style="--to: 12840"></span>
```

```css
@property --n { syntax: "<integer>"; initial-value: 0; inherits: false; }
.fx-count-css { --n: 0; counter-reset: n var(--n); font-variant-numeric: tabular-nums;
  animation: fx-count 1.6s cubic-bezier(.2, .8, .2, 1) forwards; }
.fx-count-css::after { content: counter(n); }
@keyframes fx-count { to { --n: var(--to); } }
html[data-capture] .fx-count-css { animation: none; --n: var(--to); }
```

### typing

```html
<span class="fx-typing" data-text="Hello, Swift!">Hello, Swift!</span>
<script>
(() => {
  const settled = document.documentElement.hasAttribute('data-capture');
  document.querySelectorAll('.fx-typing').forEach(el => {
    if (el.dataset.fx) return; el.dataset.fx = 1;
    const full = el.dataset.text;
    if (settled) { el.textContent = full; return; }                  // PNG, reduced motion: full text
    el.textContent = '';
    let i = 0;
    const timer = setInterval(() => {
      el.textContent = full.slice(0, ++i);
      if (i >= full.length) clearInterval(timer);
    }, 60);
  });
})();
</script>
```

```css
.fx-typing::after { content: ""; display: inline-block; width: 2px; height: 1em; margin-left: 2px;
  vertical-align: -.12em; background: var(--accent); animation: fx-caret .7s step-end infinite; }
@keyframes fx-caret { 50% { opacity: 0; } }
html[data-capture] .fx-typing::after { display: none; }
```

### scramble

The characters scramble, then lock in from the left. The final text is the element's original text.

```html
<span class="fx-scramble">DECODING COMPLETE</span>
<script>
(() => {
  const settled = document.documentElement.hasAttribute('data-capture');
  if (settled) return;                                               // PNG, reduced motion: the markup already has the final text
  const glyphs = '!<>-_\\/[]{}=+*^?#';
  document.querySelectorAll('.fx-scramble').forEach(el => {
    if (el.dataset.fx) return; el.dataset.fx = 1;
    const full = el.textContent;
    const t0 = performance.now(), per = 60;
    requestAnimationFrame(function tick(t) {
      const fixed = Math.floor((t - t0) / per);
      el.textContent = [...full].map((c, i) =>
        i < fixed || c === ' ' ? c : glyphs[Math.floor(Math.random() * glyphs.length)]).join('');
      if (fixed < full.length) requestAnimationFrame(tick);
    });
  });
})();
</script>
```

### gradient text

```html
<span class="fx-grad">Dynamic</span>
```

```css
.fx-grad { font-weight: 800;
  background: linear-gradient(90deg, var(--accent), var(--purple), var(--orange), var(--accent));
  background-size: 300% 100%; -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: fx-grad 4s linear infinite; }
@keyframes fx-grad { to { background-position: -300% 0; } }
html[data-capture] .fx-grad { animation: none; background-position: 0 0; }
```

## (c) Interaction feedback (HTML only): hover/press, ripple, 3D tilt, card flip

In the PNG they are all in the rest state. With reduced motion, the transitions are turned off.

### hover / press

```html
<button class="fx-press">Start brew</button>
<div class="fx-row">Ethiopia Guji</div>
```

```css
.fx-press { cursor: pointer; transition: transform .15s ease-out, filter .15s; }
.fx-press:hover { filter: brightness(1.06); }
.fx-press:active { transform: scale(.96); }
.fx-row { border-radius: 6px; transition: background-color .15s; }
.fx-row:hover { background: var(--fill); }
.fx-row:active { background: rgba(120, 120, 128, .2); }
html[data-capture] .fx-press, html[data-capture] .fx-row { transition: none; }
```

### ripple

```html
<button class="fx-ripple">Tap me</button>
<script>
(() => {
  if (document.documentElement.hasAttribute('data-capture')) return;  // rest only; no listener in settled mode
  document.querySelectorAll('.fx-ripple').forEach(btn => {
    if (btn.dataset.fx) return; btn.dataset.fx = 1;
    btn.addEventListener('click', e => {
      const r = btn.getBoundingClientRect(), size = Math.max(r.width, r.height) * 2;
      const s = document.createElement('span');
      s.className = 'fx-rp';
      s.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - r.left - size / 2}px;top:${e.clientY - r.top - size / 2}px`;
      btn.appendChild(s);
      s.addEventListener('animationend', () => s.remove());
    });
  });
})();
</script>
```

```css
.fx-ripple { position: relative; overflow: hidden; }
.fx-rp { position: absolute; border-radius: 50%; background: rgba(255, 255, 255, .5);
  transform: scale(0); animation: fx-rp .6s ease-out forwards; pointer-events: none; }
@keyframes fx-rp { to { transform: scale(1); opacity: 0; } }
```

### 3D tilt

```html
<div class="fx-tilt-wrap"><div class="fx-tilt">Hover me</div></div>
<script>
(() => {
  if (document.documentElement.hasAttribute('data-capture')) return;  // rest only
  document.querySelectorAll('.fx-tilt').forEach(el => {
    if (el.dataset.fx) return; el.dataset.fx = 1;
    el.addEventListener('mousemove', e => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      el.classList.remove('fx-leave');
      el.style.transform = `rotateY(${x * 20}deg) rotateX(${-y * 20}deg)`;
    });
    el.addEventListener('mouseleave', () => { el.classList.add('fx-leave'); el.style.transform = ''; });
  });
})();
</script>
```

```css
.fx-tilt-wrap { perspective: 700px; display: inline-block; }
.fx-tilt { padding: 24px 32px; border-radius: 14px; color: #fff; font-weight: 600;
  background: linear-gradient(135deg, var(--accent), var(--purple));
  box-shadow: 0 8px 20px rgba(0, 0, 0, .2); transition: transform .15s ease-out; will-change: transform; }
.fx-tilt.fx-leave { transition: transform .5s ease-out; }
```

### card flip

```html
<div class="fx-flip"><div class="fx-flip-in"><div class="fx-flip-front">Front</div><div class="fx-flip-back">Back</div></div></div>
<script>
(() => {
  document.querySelectorAll('.fx-flip').forEach(el => {
    if (el.dataset.fx) return; el.dataset.fx = 1;
    el.addEventListener('click', () => el.classList.toggle('on'));
  });
})();
</script>
```

```css
.fx-flip { width: 150px; height: 96px; perspective: 600px; cursor: pointer; }
.fx-flip-in { position: relative; width: 100%; height: 100%; transform-style: preserve-3d; transition: transform .6s; }
html:not([data-capture]) .fx-flip:hover .fx-flip-in, html:not([data-capture]) .fx-flip.on .fx-flip-in { transform: rotateY(180deg); }
.fx-flip-in > div { position: absolute; inset: 0; display: grid; place-items: center; border-radius: 12px;
  backface-visibility: hidden; -webkit-backface-visibility: hidden; font-weight: 600; color: #fff; }
.fx-flip-front { background: var(--accent); }
.fx-flip-back { background: var(--purple); transform: rotateY(180deg); }
html[data-capture] .fx-flip-in { transition: none; transform: none; }
```

## (d) Transitions and scroll: scroll reveal, View Transitions shuffle, scroll-driven bar

### scroll reveal

Elements rise from below as they enter the view. Use `style="--i: N"` to stagger them in order. It also works for list rows that appear one after another on load.

```html
<div class="fx-reveal" style="--i: 0">Row one</div>
<div class="fx-reveal" style="--i: 1">Row two</div>
<script>
(() => {
  const items = [...document.querySelectorAll('.fx-reveal')].filter(el => !el.dataset.fx);
  items.forEach(el => { el.dataset.fx = 1; });
  if (document.documentElement.hasAttribute('data-capture') || !('IntersectionObserver' in window)) {
    items.forEach(el => el.classList.add('in'));                     // PNG, reduced motion: revealed
    return;
  }
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: .2 });
  items.forEach(el => io.observe(el));
})();
</script>
```

```css
.fx-reveal { opacity: 0; transform: translateY(14px);
  transition: opacity .5s ease-out, transform .5s ease-out; transition-delay: calc(var(--i, 0) * 70ms); }
.fx-reveal.in { opacity: 1; transform: none; }
html[data-capture] .fx-reveal { opacity: 1; transform: none; transition: none; }
```

### View Transitions shuffle (HTML only)

Pressing the button reorders the list smoothly. Without `startViewTransition`, it just reorders.

```html
<div class="fx-vt">
  <ul><li>Alpha</li><li>Bravo</li><li>Charlie</li><li>Delta</li></ul>
  <button class="fx-vt-btn">Shuffle</button>
</div>
<script>
(() => {
  const settled = document.documentElement.hasAttribute('data-capture');
  document.querySelectorAll('.fx-vt').forEach(box => {
    if (box.dataset.fx) return; box.dataset.fx = 1;
    const list = box.querySelector('ul'), uid = Math.random().toString(36).slice(2);
    [...list.children].forEach((li, i) => { li.style.viewTransitionName = `vt-${uid}-${i}`; });
    box.querySelector('.fx-vt-btn').addEventListener('click', () => {
      const reorder = () => {
        const items = [...list.children];
        for (let i = items.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [items[i], items[j]] = [items[j], items[i]];
        }
        items.forEach(li => list.appendChild(li));
      };
      if (document.startViewTransition && !settled) document.startViewTransition(reorder);
      else reorder();
    });
  });
})();
</script>
```

```css
.fx-vt ul { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.fx-vt li { padding: 8px 12px; border-radius: 8px; background: var(--fill); font-weight: 600; }
```

### scroll-driven bar (mainly Chrome)

The top bar fills and the box enters as the scroll position changes. It moves only in browsers that support `animation-timeline`. The final value is set with `--settled` (default 1).

Put the bar inside the scrolling inner area (`.fx-scroller`) and pin it to the top with `sticky`. It works even with `.canvas { overflow: hidden }`, because the inner area scrolls by itself.

```html
<div class="fx-scroller">
  <div class="fx-scroll-bar" style="--settled: 1"></div>
  <p>Long content ...</p>
  <div class="fx-sd">Enters with the scroll position</div>
  <p>Long content ...</p>
</div>
```

```css
.fx-scroller { position: relative; height: 320px; overflow-y: auto; }
.fx-scroll-bar { position: sticky; top: 0; height: 3px; background: var(--accent); z-index: 10;
  transform: scaleX(var(--settled, 1)); transform-origin: left; }   /* unsupported browsers: shows the final value */
@media (prefers-reduced-motion: no-preference) {
  @supports (animation-timeline: scroll()) {
    .fx-scroll-bar { animation: fx-grow linear both; animation-timeline: scroll(nearest); }
    .fx-sd { animation: fx-sd-in linear both; animation-timeline: view(); animation-range: entry 0% entry 80%; }
    @keyframes fx-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
    @keyframes fx-sd-in { from { opacity: 0; transform: translateY(40px) scale(.95); } to { opacity: 1; transform: none; } }
  }
}
html[data-capture] .fx-scroll-bar { animation: none; transform: scaleX(var(--settled, 1)); }
html[data-capture] .fx-sd { animation: none; opacity: 1; transform: none; }
```

It has no meaning in a mockup without a scrolling inner area. Use scroll reveal there.
