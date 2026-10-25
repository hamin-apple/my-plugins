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

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var timer: Timer?
    let queue = DispatchQueue(label: "poll")
    var shown: [MenuItem]?
    var menuOpen = false
    var pending: MenuState?

    func applicationDidFinishLaunching(_ note: Notification) {
        item.button?.image = NSImage(systemSymbolName: "list.bullet.rectangle", accessibilityDescription: "my-agent monitor")
        item.button?.imagePosition = .imageLeft
        render(.off)
        launch(command(.start, python: pythonPath, root: monitorRoot))   // server only, no window
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
    }

    func poll() {
        queue.async {
            let state = queryState(ports: portRange, env: env)
            DispatchQueue.main.async { self.render(state) }
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
        item.menu = menu
    }

    func menuWillOpen(_ menu: NSMenu) { menuOpen = true }

    func menuDidClose(_ menu: NSMenu) {
        menuOpen = false
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
