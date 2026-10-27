// The mini window: one lazily built window, per-mode frames, pin level.
import AppKit
import Combine
import SwiftUI

/// The first click on an inactive window activates it and counts as a click.
final class FirstClickWindow: NSWindow {
    override func sendEvent(_ event: NSEvent) {
        if event.type == .leftMouseDown, !isKeyWindow {
            NSApp.activate(ignoringOtherApps: true)
            makeKeyAndOrderFront(nil)
        }
        super.sendEvent(event)
    }
}

final class WindowController: NSObject, NSWindowDelegate {
    let store: Store
    private var window: FirstClickWindow?
    private var cancellables = Set<AnyCancellable>()
    private var applyingFrame = false
    private var currentMode: Mode

    private static let defaultSize: [Mode: NSSize] = [.list: NSSize(width: 300, height: 640), .detail: NSSize(width: 1000, height: 700)]
    private static let minContent: [Mode: NSSize] = [.list: NSSize(width: 260, height: 240), .detail: NSSize(width: 720, height: 420)]

    init(store: Store) {
        self.store = store
        currentMode = store.mode
        super.init()
    }

    /// Opens the window or brings it to the front, also when another app is active.
    func show() {
        let win = window ?? makeWindow()
        if win.isMiniaturized { win.deminiaturize(nil) }
        NSApp.activate(ignoringOtherApps: true)
        win.makeKeyAndOrderFront(nil)
    }

    private func makeWindow() -> FirstClickWindow {
        let win = FirstClickWindow(contentRect: NSRect(origin: .zero, size: Self.defaultSize[store.mode]!),
                                   styleMask: [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView],
                                   backing: .buffered, defer: false)
        win.titleVisibility = .hidden
        win.titlebarAppearsTransparent = true
        win.isMovableByWindowBackground = true
        win.isReleasedWhenClosed = false
        win.collectionBehavior = [.moveToActiveSpace]
        win.delegate = self
        let hosting = NSHostingView(rootView: RootView(store: store))
        hosting.sizingOptions = []   // the window size is ours, not the content's
        win.contentView = hosting
        window = win
        currentMode = store.mode
        applyingFrame = true
        applyFrame(store.mode)
        applyingFrame = false
        win.level = store.pinned ? .floating : .normal
        store.$pinned.dropFirst().sink { [weak self] on in self?.window?.level = on ? .floating : .normal }.store(in: &cancellables)
        store.$mode.dropFirst().sink { [weak self] m in self?.switchMode(m) }.store(in: &cancellables)
        return win
    }

    private func frameKey(_ m: Mode) -> String { "frame." + m.rawValue }

    private func saveFrame(_ m: Mode) {
        guard let w = window else { return }
        settings.set(NSStringFromRect(w.frame), forKey: frameKey(m))
    }

    private func applyFrame(_ m: Mode) {
        guard let w = window else { return }
        w.contentMinSize = Self.minContent[m]!
        if let text = settings.string(forKey: frameKey(m)) {
            let saved = NSRectFromString(text)
            if saved.width > 0, saved.height > 0 {
                let screens = NSScreen.screens.map { $0.visibleFrame }
                w.setFrame(fitFrame(saved, screens: screens), display: true)
                return
            }
        }
        w.setContentSize(Self.defaultSize[m]!)
        w.center()
    }

    private func switchMode(_ m: Mode) {
        saveFrame(currentMode)
        currentMode = m
        applyingFrame = true   // no saves until the new frame is in place
        DispatchQueue.main.async {
            self.applyFrame(m)
            self.applyingFrame = false
        }
    }

    func windowDidMove(_ notification: Notification) {
        if !applyingFrame { saveFrame(currentMode) }
    }

    func windowDidResize(_ notification: Notification) {
        if !applyingFrame { saveFrame(currentMode) }
    }
}
