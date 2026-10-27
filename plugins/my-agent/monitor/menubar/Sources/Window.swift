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
    private var listRows = 0            // rows the List shows, from the filter and list publishers
    private var refitPending = false    // a fit was asked for while a frame animation ran
    private var refitScheduled = false  // a retry is waiting for the mouse to be released

    private static let defaultSize: [Mode: NSSize] = [.list: NSSize(width: ListMetrics.defaultWidth, height: 640), .detail: NSSize(width: 1000, height: 700)]
    private static let detailMinContent = NSSize(width: 720, height: 420)
    private static let unlimited: CGFloat = 100_000

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
        listRows = visibleRowCount(store.listState, filter: store.filter)
        applyingFrame = true
        applyFrame(store.mode)
        applyingFrame = false
        win.level = store.pinned ? .floating : .normal
        store.$pinned.dropFirst().sink { [weak self] on in self?.window?.level = on ? .floating : .normal }.store(in: &cancellables)
        store.$mode.dropFirst().sink { [weak self] m in self?.switchMode(m) }.store(in: &cancellables)
        // The row count comes from the two published values themselves: @Published emits before it stores,
        // so reading store.filter or store.listState inside the sink would give the old value.
        Publishers.CombineLatest(store.$listState, store.$filter)
            .map { visibleRowCount($0, filter: $1) }
            .removeDuplicates()
            .dropFirst()
            .sink { [weak self] n in
                guard let self = self else { return }
                self.listRows = n
                if self.currentMode == .list { self.fitList() }
            }
            .store(in: &cancellables)
        return win
    }

    private func frameKey(_ m: Mode) -> String { "frame." + m.rawValue }

    private func saveFrame(_ m: Mode) {
        guard let w = window else { return }
        settings.set(NSStringFromRect(w.frame), forKey: frameKey(m))
    }

    private func applyFrame(_ m: Mode) {
        guard let w = window else { return }
        if m == .list {
            applyListFrame(w)
            return
        }
        w.contentMinSize = Self.detailMinContent
        w.contentMaxSize = NSSize(width: Self.unlimited, height: Self.unlimited)
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

    /// Opening and mode switch: no animation. Only the saved top edge, x and width count; the height is calculated.
    private func applyListFrame(_ w: NSWindow) {
        listRows = visibleRowCount(store.listState, filter: store.filter)
        let screens = NSScreen.screens.map { $0.visibleFrame }
        var anchor: CGRect?
        if let text = settings.string(forKey: frameKey(.list)) {
            let saved = NSRectFromString(text)
            if saved.width > 0, saved.height > 0 { anchor = saved }
        }
        if anchor == nil {
            let area = (NSScreen.main?.visibleFrame ?? screens.first ?? NSRect(x: 0, y: 0, width: 1440, height: 900))
            let want = listContentHeight(rows: listRows)
            anchor = CGRect(x: area.midX - ListMetrics.defaultWidth / 2, y: area.midY - want / 2,
                            width: ListMetrics.defaultWidth, height: want)
        }
        let target = listFrame(anchor: anchor!, rows: listRows, screens: screens).frame
        releaseListHeight(to: target.height)
        w.setFrame(target, display: true)
        lockListHeight(target.height)
    }

    /// Width stays free, the height is fixed: the user can only change the width.
    private func lockListHeight(_ frameHeight: CGFloat) {
        guard let w = window else { return }
        let h = w.contentRect(forFrameRect: NSRect(x: 0, y: 0, width: 1, height: frameHeight)).height
        w.contentMinSize = NSSize(width: ListMetrics.minWidth, height: h)
        w.contentMaxSize = NSSize(width: Self.unlimited, height: h)
    }

    /// Frees the height so setFrame can change it. Locking first would make AppKit resize the window at once.
    private func releaseListHeight(to frameHeight: CGFloat) {
        guard let w = window else { return }
        let target = w.contentRect(forFrameRect: NSRect(x: 0, y: 0, width: 1, height: frameHeight)).height
        let now = w.contentRect(forFrameRect: w.frame).height
        w.contentMinSize = NSSize(width: ListMetrics.minWidth, height: min(now, target))
        w.contentMaxSize = NSSize(width: Self.unlimited, height: max(now, target))
    }

    /// Fits the List height to the visible rows with a short animation. The top edge stays.
    private func fitList() {
        guard let w = window, currentMode == .list else { return }
        if NSEvent.pressedMouseButtons != 0 || w.inLiveResize {   // do not disturb a drag
            scheduleRefit()
            return
        }
        if applyingFrame {
            refitPending = true
            return
        }
        let target = listFrame(anchor: w.frame, rows: listRows, screens: NSScreen.screens.map { $0.visibleFrame }).frame
        let cur = w.frame
        if abs(target.minX - cur.minX) < 0.5, abs(target.minY - cur.minY) < 0.5,
           abs(target.width - cur.width) < 0.5, abs(target.height - cur.height) < 0.5 {
            lockListHeight(target.height)
            return
        }
        applyingFrame = true
        releaseListHeight(to: target.height)
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.15
            w.animator().setFrame(target, display: true)
        }, completionHandler: { [weak self] in
            guard let self = self else { return }
            self.lockListHeight(target.height)
            self.applyingFrame = false
            self.saveFrame(.list)
            if self.refitPending {
                self.refitPending = false
                self.fitList()
            }
        })
    }

    private func scheduleRefit() {
        if refitScheduled { return }
        refitScheduled = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.refitScheduled = false
            self?.fitList()
        }
    }

    private func switchMode(_ m: Mode) {
        saveFrame(currentMode)
        currentMode = m
        applyingFrame = true   // no saves until the new frame is in place
        DispatchQueue.main.async {
            self.applyFrame(m)
            self.applyingFrame = false
            if self.refitPending {
                self.refitPending = false
                self.fitList()
            }
        }
    }

    func windowDidMove(_ notification: Notification) {
        if !applyingFrame { saveFrame(currentMode) }
    }

    func windowDidEndLiveResize(_ notification: Notification) {
        if currentMode == .list { fitList() }
    }

    /// A lower screen has a lower limit (criterion 3).
    func windowDidChangeScreen(_ notification: Notification) {
        if currentMode == .list { fitList() }
    }

    func windowDidResize(_ notification: Notification) {
        if !applyingFrame { saveFrame(currentMode) }
    }
}
