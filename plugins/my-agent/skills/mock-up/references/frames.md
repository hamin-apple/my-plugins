# Device frames

Wrap a screen in a phone, laptop, macOS window, or browser frame. Plain CSS, no image assets. All sizes assume `* { box-sizing: border-box }` from `templates/canvas.html`. Colors come from the `:root` tokens of that template (SF font, Apple system colors; the old names `--surface`, `--text`, `--muted`, `--line` are aliases).

Swift default: a mobile app uses the Phone frame with the iOS elements below; a web app uses the macOS window. A style the user states wins.

## Phone (screen 390x844, frame 438x892)

Set `mockup-size` (and `--w`/`--h`) to about 900x1000 for one phone, centered with flex.

```html
<div class="phone">
  <div class="screen">
    <div class="island"></div>
    <div class="statusbar"><span>9:41</span><span>5G ▮▮▮</span></div>
    <!-- screen content -->
    <div class="homebar"></div>
  </div>
</div>
```

```css
.canvas { display: flex; align-items: center; justify-content: center; }
.phone { width: 438px; height: 892px; padding: 24px; border-radius: 64px;
  background: #111; box-shadow: 0 30px 60px rgba(0,0,0,.25); }
.phone .screen { width: 390px; height: 844px; border-radius: 40px; overflow: hidden;
  background: var(--bg); position: relative; }
.island { position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
  width: 120px; height: 34px; border-radius: 20px; background: #000; z-index: 2; }
.statusbar { height: 54px; padding: 18px 28px 0; display: flex; justify-content: space-between;
  font: 600 15px var(--font); }
.homebar { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%);
  width: 134px; height: 5px; border-radius: 3px; background: var(--text); opacity: .85; }
```

The island, status bar and home bar live inside `.screen`, so `top: 12px` is measured from the screen edge. Keep the top 54px of the screen free for the status bar.

### iOS look inside the phone (default for mobile apps)

Large title below the status bar, grouped list on `--bg`, tab bar above the home bar (leave about 34px at the bottom for the home bar).

```html
<h1 class="large-title">Brews</h1>
<div class="group">
  <div class="cell"><span>Ethiopia Guji</span><span class="detail">18 g · 4:00</span></div>
  <div class="cell"><span>Colombia Huila</span><span class="detail">16 g · 3:30</span></div>
</div>
<nav class="tabbar"><span class="on">Brews</span><span>Timer</span><span>Beans</span><span>Settings</span></nav>
```

```css
.large-title { font: 700 34px/1.2 var(--font); padding: 8px 20px 12px; }
.group { margin: 0 16px 20px; background: var(--grouped-bg); border-radius: var(--radius); overflow: hidden; }
.cell { display: flex; justify-content: space-between; align-items: center; min-height: 44px; padding: 0 16px;
  font-size: 17px; }
.cell + .cell { border-top: .5px solid var(--separator); }
.cell .detail { color: var(--secondary-label); }
.tabbar { position: absolute; left: 0; right: 0; bottom: 0; height: 83px; padding-top: 8px; display: flex;
  justify-content: space-around; align-items: flex-start; font-size: 10px; color: var(--secondary-label);
  background: var(--material); border-top: .5px solid var(--separator); }
.tabbar .on { color: var(--accent); }
```

## Laptop (screen 1280x800, mockup-size about 1700x1050)

Use this only when the user asks for a laptop. A web app without that request uses the macOS window below.

```html
<div class="laptop">
  <div class="lid"><div class="screen"><!-- content --></div></div>
  <div class="base"></div>
</div>
```

```css
.canvas { display: flex; align-items: center; justify-content: center; }
.laptop { display: flex; flex-direction: column; align-items: center; }
.laptop .lid { width: 1320px; height: 840px; padding: 20px; background: #1a1a1a; border-radius: 22px 22px 0 0; }
.laptop .screen { width: 1280px; height: 800px; overflow: hidden; background: var(--bg); border-radius: 6px; }
.laptop .base { width: 1560px; height: 22px; background: linear-gradient(#d9d9dc, #b9b9bd);
  border-radius: 0 0 24px 24px; }
```

## macOS window (default for web apps; window 1280x800, mockup-size = window plus 80px margin)

A native-looking Mac app window: traffic lights, toolbar, translucent sidebar, content area. Sizes: window 1280x800, titlebar and toolbar in one row 52px high, sidebar 232px wide, the content area takes the rest (1048px wide, 748px high). `mockup-size` (and `--w`/`--h`) is the window plus the board padding around it: 1360x880 for one window with 40px around it.

```html
<div class="mac-window">
  <div class="mac-titlebar">
    <span class="light red"></span><span class="light yellow"></span><span class="light green"></span>
    <div class="mac-toolbar">
      <b class="mac-title">Brew Log</b>
      <div class="mac-seg"><span class="on">List</span><span>Grid</span></div>
      <div class="mac-search">Search</div>
      <span class="mac-btn">+</span>
    </div>
  </div>
  <div class="mac-body">
    <aside class="mac-sidebar">
      <div class="mac-sec">Library</div>
      <div class="mac-row sel"><i class="mac-ico"></i>All Brews</div>
      <div class="mac-row"><i class="mac-ico"></i>Favorites</div>
      <div class="mac-sec">Beans</div>
      <div class="mac-row"><i class="mac-ico"></i>Ethiopia Guji</div>
    </aside>
    <main class="mac-content"><!-- list + detail columns --></main>
  </div>
</div>
```

```css
.canvas { display: flex; align-items: center; justify-content: center; }
.mac-window { width: 1280px; height: 800px; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column;
  background: var(--grouped-bg); border: .5px solid rgba(0,0,0,.25);
  box-shadow: 0 22px 60px rgba(0,0,0,.28), 0 0 0 .5px rgba(0,0,0,.1); }
.mac-titlebar { height: 52px; flex: none; display: flex; align-items: center; gap: 8px; padding: 0 16px;
  background: var(--material); border-bottom: .5px solid var(--separator); }
.mac-titlebar .light { width: 12px; height: 12px; border-radius: 50%; display: block; flex: none; }
.light.red { background: #ff5f57; } .light.yellow { background: #febc2e; } .light.green { background: #28c840; }
.mac-toolbar { flex: 1; display: flex; align-items: center; gap: 14px; margin-left: 16px; }
.mac-title { font: 600 14px var(--font); margin-right: auto; }
.mac-seg { display: flex; padding: 2px; border-radius: 7px; background: var(--fill); font-size: 12px; }
.mac-seg span { padding: 2px 12px; border-radius: 5px; }
.mac-seg .on { background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.18); }
.mac-search { width: 180px; height: 28px; border-radius: 7px; background: var(--fill); padding: 0 10px;
  font: 13px/28px var(--font); color: var(--secondary-label); }
.mac-btn { width: 28px; height: 28px; border-radius: 7px; background: var(--fill); text-align: center;
  font: 16px/28px var(--font); }
.mac-body { flex: 1; display: flex; min-height: 0; }
.mac-sidebar { width: 232px; flex: none; padding: 12px 10px; background: var(--sidebar-bg);
  border-right: .5px solid var(--separator); font-size: 13px; }
.mac-sec { padding: 10px 8px 4px; font: 600 11px var(--font); color: var(--secondary-label); }
.mac-row { height: 28px; display: flex; align-items: center; gap: 8px; padding: 0 8px; border-radius: 6px; }
.mac-row.sel { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent); }
.mac-ico { display: block; width: 16px; height: 16px; border-radius: 4px; background: var(--accent); flex: none; }
.mac-content { flex: 1; min-width: 0; overflow: hidden; background: var(--grouped-bg); }
```

## Browser window (no device; mockup-size = window size plus 80px margin)

Use this only when the user asks for a browser (URL bar). A web app without that request uses the macOS window above.

```html
<div class="browser">
  <div class="bar">
    <i class="dot" style="background:#ff5f57"></i><i class="dot" style="background:#febc2e"></i><i class="dot" style="background:#28c840"></i>
    <div class="url">app.example.com/dashboard</div>
  </div>
  <div class="page"><!-- content --></div>
</div>
```

```css
.canvas { display: flex; align-items: center; justify-content: center; }
.browser { width: 1280px; height: 800px; border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
  background: var(--surface); box-shadow: 0 20px 50px rgba(0,0,0,.15); display: flex; flex-direction: column; }
.browser .bar { height: 44px; flex: none; display: flex; align-items: center; gap: 8px; padding: 0 14px;
  background: #ececee; border-bottom: 1px solid var(--line); }
.browser .dot { width: 12px; height: 12px; border-radius: 50%; display: block; }
.browser .url { flex: 1; height: 28px; border-radius: 8px; background: #fff; margin: 0 16px;
  font: 13px/28px var(--font); color: var(--muted); padding: 0 12px; }
.browser .page { flex: 1; overflow: hidden; background: var(--bg); }
```

## Presentation background

For promo-style output, put a soft gradient on `.canvas`: `background: linear-gradient(135deg, #dfe7ff, #f6e9ff);`.
