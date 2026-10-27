// my-agent menu bar app: running task count, one line per running task, opens the monitor via monitor-up.py.
import AppKit
import Foundation

let env = ProcessInfo.processInfo.environment
let args = Array(CommandLine.arguments.dropFirst())
var portRange = 8765...8775
if let i = args.firstIndex(of: "--ports"), i + 1 < args.count, let r = parsePorts(args[i + 1]) { portRange = r }

func launch(_ argv: [String]) {
    guard let exe = argv.first else { return }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: exe)
    p.arguments = Array(argv.dropFirst())
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    try? p.run()   // not awaited; monitor-up.py always exits 0
}

if args.contains("--print-menu") {
    let state = queryState(ports: portRange, env: env)
    print(renderMenu(state, browser: readBrowser(env: env), python: pythonPath, root: monitorRoot))
    exit(0)
}

func usageExit(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

func parseRect(_ text: String) -> CGRect? {
    let v = text.split(separator: ",", omittingEmptySubsequences: false).map { Double($0) }
    guard v.count == 4, !v.contains(where: { $0 == nil || !$0!.isFinite }) else { return nil }
    guard v[2]! > 0, v[3]! > 0 else { return nil }
    return CGRect(x: v[0]!, y: v[1]!, width: v[2]!, height: v[3]!)
}

if args.contains("--print-list") {
    var filter = ListFilter.all
    if let i = args.firstIndex(of: "--filter") {
        guard i + 1 < args.count, let f = ListFilter(rawValue: args[i + 1]) else {
            usageExit("--filter needs all, running, done or stopped")
        }
        filter = f
    }
    var state = ListState.off
    if let found = queryTasks(ports: portRange, env: env), let rows = parseTasks(found.data) { state = .on(rows) }
    print(renderList(state, filter: filter, tones: args.contains("--tones")))
    exit(0)
}

if let i = args.firstIndex(of: "--fit-frame") {
    let rects = args[(i + 1)...].map(parseRect)
    guard rects.count >= 2, !rects.contains(where: { $0 == nil }) else {
        usageExit("--fit-frame needs <x,y,w,h> <x,y,w,h>...: the saved frame, then one or more screens")
    }
    let r = fitFrame(rects[0]!, screens: rects.dropFirst().map { $0! })
    print([r.minX, r.minY, r.width, r.height].map { String(Int($0.rounded())) }.joined(separator: ","))
    exit(0)
}

if let i = args.firstIndex(of: "--list-frame") {
    let rest = Array(args[(i + 1)...])
    guard rest.count >= 3, let anchor = parseRect(rest[0]), let rows = Int(rest[1]), rows >= 0 else {
        usageExit("--list-frame needs <x,y,w,h> <rows> <x,y,w,h>...: the frame, the row count (0 or more), then one or more screens")
    }
    let screens = rest.dropFirst(2).map(parseRect)
    guard !screens.contains(where: { $0 == nil }) else { usageExit("--list-frame: bad screen rectangle") }
    let r = listFrame(anchor: anchor, rows: rows, screens: screens.map { $0! })
    let f = r.frame
    print([f.minX, f.minY, f.width, f.height].map { String(Int($0.rounded())) }.joined(separator: ",") + (r.scrolls ? " scroll" : " fit"))
    exit(0)
}

if args.contains("--print-palette") {
    for p in statusPalette { print("\(p.tone.rawValue)\t\(p.light)\t\(p.dark)") }
    exit(0)
}

if let i = args.firstIndex(of: "--print-detail") {
    var kv: [String: String] = [:]
    for a in args[(i + 1)...] {
        guard let eq = a.firstIndex(of: "=") else { usageExit("--print-detail: bad argument \(a)") }
        kv[String(a[..<eq])] = String(a[a.index(after: eq)...])
    }
    var loaded: Int?
    var port: Int?
    guard let l = kv["loaded"], l == "none" || Int(l) != nil, let p = kv["port"], p == "off" || Int(p) != nil,
          let applied = kv["applied"].flatMap({ Int($0) }), let seq = kv["seq"].flatMap({ Int($0) }) else {
        usageExit("--print-detail loaded=<port|none> port=<port|off> applied=<n> seq=<n> [key=<key>]")
    }
    loaded = Int(l)
    port = Int(p)
    switch detailAction(loadedPort: loaded, port: port, appliedSeq: applied, seq: seq, key: kv["key"]) {
    case .off: print("off")
    case .load(let url): print("load " + url)
    case .select(let js): print("select " + js)
    case .none: print("none")
    }
    exit(0)
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var timer: Timer?
    let queue = DispatchQueue(label: "poll")
    var shown: [MenuItem]?
    var menuOpen = false
    var pending: MenuState?
    var menu: NSMenu?   // kept here, hung on the item only for a right/Ctrl click
    let store = Store()
    lazy var windows = WindowController(store: store)

    func applicationDidFinishLaunching(_ note: Notification) {
        item.button?.image = NSImage(systemSymbolName: "list.bullet.rectangle", accessibilityDescription: "my-agent monitor")
        item.button?.imagePosition = .imageLeft
        item.button?.target = self
        item.button?.action = #selector(clicked(_:))
        item.button?.sendAction(on: [.leftMouseDown, .rightMouseUp])   // left on down: the window order is read before the click changes it
        // The window order is read again when the pointer enters the icon, before a click can change it.
        item.button?.addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                                    owner: self, userInfo: nil))
        render(.off)
        launch(command(.start, python: pythonPath, root: monitorRoot))   // server only, no window
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
    }

    func poll() {
        queue.async {
            // one lookup per poll feeds both the menu and the list
            let found = queryTasks(ports: portRange, env: env)
            var state = MenuState.off
            var list = ListState.off
            if let f = found {
                if let running = parseRunning(f.data) { state = .on(running) }
                if let rows = parseTasks(f.data) { list = .on(rows) }
            }
            DispatchQueue.main.async {
                self.render(state)
                self.store.update(port: found?.port, list: list)
            }
        }
    }

    func render(_ state: MenuState) {
        item.button?.title = " " + iconText(state)
        item.button?.appearsDisabled = (state == .off)
        let items = menuItems(state, browser: readBrowser(env: env), python: pythonPath, root: monitorRoot)
        if items == shown { pending = nil; return }   // unchanged: keep the current menu, drop a stale pending state
        if menuOpen { pending = state; return }   // never rebuild while the menu is open
        shown = items
        let menu = NSMenu()
        menu.delegate = self
        for m in items {
            switch m.kind {
            case .separator:
                menu.addItem(.separator())
            case .quit:
                let mi = NSMenuItem(title: m.title, action: #selector(quit), keyEquivalent: "")
                mi.target = self
                menu.addItem(mi)
            case .browser:
                let sub = NSMenu()
                for c in m.choices {
                    let ci = NSMenuItem(title: c.title, action: #selector(run(_:)), keyEquivalent: "")
                    ci.target = self
                    ci.state = c.selected ? .on : .off
                    ci.representedObject = c.argv
                    sub.addItem(ci)
                }
                let mi = NSMenuItem(title: m.title + " ▸", action: nil, keyEquivalent: "")
                mi.submenu = sub
                menu.addItem(mi)
            default:
                let mi = NSMenuItem(title: m.title, action: m.enabled ? #selector(run(_:)) : nil, keyEquivalent: "")
                mi.target = self
                mi.isEnabled = m.enabled
                mi.representedObject = m.argv
                menu.addItem(mi)
            }
        }
        self.menu = menu
    }

    @objc func mouseEntered(with event: NSEvent) { windows.noteHover() }

    @objc func clicked(_ sender: Any?) {
        let e = NSApp.currentEvent
        let menuClick = e?.type == .rightMouseUp || (e?.modifierFlags.contains(.control) ?? false)
        if menuClick, let m = menu {
            item.menu = m
            item.button?.performClick(nil)   // shows the menu
        } else if !menuClick {
            windows.toggle()
        }
    }

    func menuWillOpen(_ menu: NSMenu) { menuOpen = true }

    func menuDidClose(_ menu: NSMenu) {
        menuOpen = false
        DispatchQueue.main.async { self.item.menu = nil }   // later, so the chosen item still runs
        if let s = pending { pending = nil; render(s) }
    }

    @objc func run(_ sender: NSMenuItem) {
        if let argv = sender.representedObject as? [String] { launch(argv) }
    }

    @objc func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
