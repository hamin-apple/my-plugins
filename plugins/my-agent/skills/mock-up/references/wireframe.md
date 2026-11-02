# Wireframe

Low-fidelity structure sketch. Layout and hierarchy only; no brand color, no imagery.

## Rules

- Grayscale only. The one exception is the numbered annotation badge, which uses a single red so notes stand out from the sketch.
- One font (system sans). Text is real but short: labels such as "Search", "Order total", "Continue".
- Images are a box with a diagonal cross. Avatars are circles. Charts are a labeled box ("Line chart: revenue, 30 days").
- Buttons: primary is filled dark with white text, secondary is outlined. No other emphasis.
- Add numbered annotation badges (1, 2, 3) on key elements and a legend column on the right when the user asks for annotations or the screen has non-obvious behavior.
- Use an 8px grid and align everything.

## Starter CSS (replace the `:root` block of `templates/canvas.html`, append the rest)

```css
:root {
  --w: 1440px; --h: 900px;
  --bg: #f4f4f4; --surface: #ffffff; --text: #333333; --muted: #888888;
  --line: #bdbdbd; --fill: #e6e6e6; --radius: 4px;
  --font: -apple-system, "Helvetica Neue", "Apple SD Gothic Neo", Arial, sans-serif;
}
.box { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; }
.btn { display: inline-block; padding: 8px 16px; border: 1px solid var(--text); border-radius: var(--radius); }
.btn.primary { background: var(--text); color: #fff; }
.input { height: 36px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface);
  padding: 0 12px; color: var(--muted); display: flex; align-items: center; }
.avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--fill); border: 1px solid var(--line); }
.ph-img { background: var(--fill); border: 1px solid var(--line); position: relative; }
.ph-img::before, .ph-img::after {
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(to top right, transparent calc(50% - .5px), var(--line) 50%, transparent calc(50% + .5px));
}
.ph-img::after { transform: scaleX(-1); }
.ph-line { height: 8px; background: var(--fill); border-radius: 4px; }   /* text placeholder */
.legend { position: absolute; right: 0; top: 0; bottom: 0; width: 280px; padding: 24px;
  border-left: 1px solid var(--line); background: var(--surface); }
.badge { width: 20px; height: 20px; border-radius: 50%; background: #e4572e; color: #fff;
  font: 600 11px/20px var(--font); text-align: center; position: absolute; }
```
