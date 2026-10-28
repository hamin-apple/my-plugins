// The mini window: one lazily built window, per-mode frames, pin level.
import AppKit
import Combine
import SwiftUI

/// The first click on an inactive window activates it and counts as a click.
/// AppKit drops that click when the clicked view does not accept first mouse. The hosting view does
/// (FirstClickHostingView), but the List rows sit in SwiftUI's scroll container, which does not:
/// for those the click (down and up) is posted again once the button is released in place and the window is key.
/// A drag that starts there (moving more than 4 pt) is not replayed.
final class FirstClickWindow: NSWindow {
    private var pendingDown: (at: NSPoint, screen: NSPoint)?   // a dropped first click, until its mouse-up
    private var pendingClick: NSPoint?                          // a released click, until the window is key

    override func sendEvent(_ event: NSEvent) {
        if event.type == .leftMouseDown {
            pendingDown = nil
            pendingClick = nil
            if !isKeyWindow {
                if dropsFirstClick(event) { pendingDown = (event.locationInWindow, NSEvent.mouseLocation) }
                NSApp.activate()   // activate(ignoringOtherApps:) was often refused, leaving the other app active
                makeKeyAndOrderFront(nil)
            }
        } else if event.type == .leftMouseUp, let down = pendingDown {
            pendingDown = nil
            let moved = hypot(NSEvent.mouseLocation.x - down.screen.x, NSEvent.mouseLocation.y - down.screen.y)
            if moved <= 4 {
                pendingClick = down.at
                if isKeyWindow { replayClick() }
                // Activation can finish later (becomeKey replays then); forget the click if it never does.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.pendingClick = nil }
            }
        }
        super.sendEvent(event)
    }

    override func becomeKey() {
        super.becomeKey()
        replayClick()
    }

    private func replayClick() {
        guard let at = pendingClick else { return }
        pendingClick = nil
        for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
            if let e = NSEvent.mouseEvent(with: type, location: at, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                          windowNumber: windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1) {
                NSApp.postEvent(e, atStart: false)
            }
        }
    }

    /// True when the view under the click does not accept first mouse, so AppKit would drop it.
    private func dropsFirstClick(_ event: NSEvent) -> Bool {
        guard let content = contentView, let parent = content.superview,
              let hit = content.hitTest(parent.convert(event.locationInWindow, from: nil)) else { return false }
        return !hit.acceptsFirstMouse(for: event)
    }
}

/// AppKit drops the first click on an inactive window unless the clicked view accepts it.
/// The filter, the List/Detail switch and the pin are SwiftUI taps directly in this view.
final class FirstClickHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
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
    /// When the app last resigned active with the window in front. A menu bar click can make the app
    /// resign (and raise the other app's windows) before the click reaches toggle().
    private var resignedInFront: Date?
    /// When the pointer last entered the menu bar icon with the window in front (see noteHover).
    private var hoveredInFront: Date?

    private static let defaultSize: [Mode: NSSize] = [.list: NSSize(width: ListMetrics.defaultWidth, height: 640), .detail: NSSize(width: 1000, height: 700)]
    private static let detailMinContent = NSSize(width: 720, height: 420)
    private static let unlimited: CGFloat = 100_000

    init(store: Store) {
        self.store = store
        currentMode = store.mode
        super.init()
        NotificationCenter.default.addObserver(forName: NSApplication.willResignActiveNotification, object: nil, queue: .main) { [weak self] _ in
            guard let self = self, let win = self.window else { return }
            self.resignedInFront = win.isVisible && !win.isMiniaturized && self.isInFront(win) ? Date() : nil
        }
    }

    /// Left click on the icon: hides the window when it is in front, else opens it or brings it to the front.
    func toggle() {
        let justResigned = resignedInFront.map { Date().timeIntervalSince($0) < 1 } ?? false
        let hovered = hoveredInFront.map { Date().timeIntervalSince($0) < 10 } ?? false
        resignedInFront = nil
        hoveredInFront = nil
        if let win = window, win.isVisible, !win.isMiniaturized, win.isOnActiveSpace, justResigned || hovered || isInFront(win) {
            win.orderOut(nil)
            if NSApp.isActive { NSApp.hide(nil) }   // gives the focus back to the app that had it (ignored when inactive)
        } else {
            show()
        }
    }

    /// The pointer entered the menu bar icon: remember whether the window is in front now. When this app is not
    /// active, a click on the icon can raise the active app's windows over it before toggle() runs.
    func noteHover() {
        guard let win = window, win.isVisible, !win.isMiniaturized, isInFront(win) else { hoveredInFront = nil; return }
        hoveredInFront = Date()
    }

    /// In front: pinned (always above), or no other window above it overlaps it (below the Dock level:
    /// the Dock and the menu bar keep transparent full-screen windows).
    /// Not NSApp.isActive: a status item click does not always make the app active.
    private func isInFront(_ win: NSWindow) -> Bool {
        if store.pinned { return true }
        guard let above = CGWindowListCopyWindowInfo([.optionOnScreenAboveWindow, .excludeDesktopElements],
                                                     CGWindowID(win.windowNumber)) as? [[String: Any]] else { return true }
        // CG bounds have the origin at the top left of the main screen
        let top = NSScreen.screens.first?.frame.maxY ?? 0
        let mine = CGRect(x: win.frame.minX, y: top - win.frame.maxY, width: win.frame.width, height: win.frame.height)
        return !above.contains { info in
            let layer = info[kCGWindowLayer as String] as? Int ?? 0
            let alpha = info[kCGWindowAlpha as String] as? Double ?? 1
            guard layer >= 0, layer < Int(CGWindowLevelForKey(.dockWindow)), alpha > 0,
                  let b = info[kCGWindowBounds as String] as? NSDictionary,
                  let r = CGRect(dictionaryRepresentation: b) else { return false }
            return r.intersects(mine)
        }
    }

    /// Opens the window or brings it to the front, also when another app is active.
    func show() {
        let win = window ?? makeWindow()
        if NSApp.isHidden { NSApp.unhide(nil) }
        if win.isMiniaturized { win.deminiaturize(nil) }
        NSApp.activate()   // activate(ignoringOtherApps:) was often refused for a status item click
        win.makeKeyAndOrderFront(nil)
        win.orderFrontRegardless()   // above the active app's windows also when macOS does not let this app activate
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
        let hosting = FirstClickHostingView(rootView: RootView(store: store))
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

    /// The Components window goes with the main window.
    func windowWillClose(_ notification: Notification) {
        store.detail.comp.closeWindow()
    }
}
