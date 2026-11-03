# Flow board

Several screens on one canvas, connected by arrows, to show a user flow. Screens are drawn at a reduced size with `.screen { width: 300px; height: 650px }` (about 0.77 of a 390x844 phone). Design the screen content for 300x650 directly; do not use `zoom`.

## Layout (3 screens, worked example)

- `mockup-size` and `--w`/`--h`: **1300x900**.
- Screen x positions: 100, 500, 900 (each 300 wide, so the gap is 100). Screen top: 130 (title above). Screen bottom: 780. Captions at y 800-840.
- Title at left 100, top 40. Optional subtitle below it (the entry point).
- Arrows run from a screen's right edge to the next screen's left edge at mid height: from x 400 to x 500 at y 455 (130 + 650/2), and from x 800 to x 900.
- For 4-5 screens widen the canvas: width = 100 + n × 300 + (n - 1) × 100 + 100. For 6+ screens use two rows (second row top at 130 + 650 + 140 = 920) and read left→right, top→bottom.

```html
<div class="canvas">
  <h1 class="title" style="left:100px;top:40px">Sign-up flow</h1>
  <div class="screen" style="left:100px;top:130px"><!-- screen 1 --></div>
  <div class="cap" style="left:100px;top:800px"><b>1</b> Enter email</div>
  <div class="screen" style="left:500px;top:130px"><!-- screen 2 --></div>
  <div class="cap" style="left:500px;top:800px"><b>2</b> Verify code</div>
  <div class="screen" style="left:900px;top:130px"><!-- screen 3 --></div>
  <div class="cap" style="left:900px;top:800px"><b>3</b> Welcome</div>
  <svg class="arrows" viewBox="0 0 1300 900"><!-- arrows --></svg>
  <span class="pill" style="left:450px;top:455px">Tap Continue</span>
</div>
```

```css
.title { position: absolute; font-size: 28px; }
.screen { position: absolute; width: 300px; height: 650px; background: var(--surface);
  border: 1px solid var(--line); border-radius: 28px; overflow: hidden; }
.cap { position: absolute; width: 300px; text-align: center; color: var(--muted); }
.cap b { display: inline-block; width: 22px; height: 22px; line-height: 22px; border-radius: 50%;
  background: var(--text); color: var(--bg); margin-right: 6px; font-size: 12px; }
.arrows { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.pill { position: absolute; transform: translate(-50%, -50%); padding: 2px 10px; border-radius: 999px;
  background: var(--surface); border: 1px solid var(--line); font-size: 12px; white-space: nowrap; }
```

## Arrows

The SVG `viewBox` must equal `mockup-size`, so coordinates match canvas pixels.

```html
<defs>
  <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" orient="auto">
    <path d="M0 0 L10 5 L0 10 z" fill="#888"/>
  </marker>
</defs>
<path d="M 400 455 L 500 455" stroke="#888" stroke-width="2" fill="none" marker-end="url(#ah)"/>
<path d="M 800 455 L 900 455" stroke="#888" stroke-width="2" fill="none" marker-end="url(#ah)"/>
```

- Put an action label (`.pill`) centered on each arrow ("Tap Continue"). Its `left`/`top` is the pill center.
- Branches: two arrows with labels ("Valid", "Error"). Keep crossings to a minimum.
- When screens are placed differently, recompute arrow endpoints from the screen positions and check the PNG for arrows touching card edges.
