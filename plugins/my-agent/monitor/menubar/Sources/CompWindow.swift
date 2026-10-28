// The Components window: the page's window.open('', 'ma-components') opens one native window that hosts the new web view.
import AppKit
import WebKit

let compDefaultSize = CGSize(width: 560, height: 640)

/// The frame the Components window opens with. A saved frame is fitted onto a visible screen; else the page's
/// requested size (or 560x640) centered on the first screen. Screens are visibleFrames.
func compOpenFrame(saved: CGRect?, size: CGSize?, screens: [CGRect]) -> CGRect {
    if let s = saved { return fitFrame(s, screens: screens) }
    let sz = size ?? compDefaultSize
    guard let area = screens.first else { return CGRect(origin: .zero, size: sz) }
    return fitFrame(CGRect(x: area.midX - sz.width / 2, y: area.midY - sz.height / 2, width: sz.width, height: sz.height), screens: screens)
}

/// Owns the one Components window and its web view. The Detail page keeps the state (`compWin`), so every close
/// is reported to it with compWinGone().
final class CompWindowController: NSObject, NSWindowDelegate {
    static let frameKey = "frame.components"
    private var window: NSWindow?
    private var child: WKWebView?
    private var applyingFrame = false
    weak var detailWeb: WKWebView?
    var pinned = false {
        didSet { window?.level = pinned ? .floating : .normal }
    }

    /// Called from the Detail web view's createWebViewWith. A second call replaces the web view in the same window.
    func host(_ web: WKWebView, features: WKWindowFeatures) -> WKWebView {
        let win: NSWindow
        if let w = window {
            win = w
        } else {
            win = NSWindow(contentRect: NSRect(origin: .zero, size: compDefaultSize),
                           styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
            win.title = "Components · my-agent"
            win.isReleasedWhenClosed = false
            win.delegate = self
            window = win
            var size: CGSize?
            if let w = features.width?.doubleValue, let h = features.height?.doubleValue, w > 0, h > 0 {
                size = win.frameRect(forContentRect: NSRect(x: 0, y: 0, width: w, height: h)).size
            }
            var saved: CGRect?
            if let text = settings.string(forKey: Self.frameKey) {
                let r = NSRectFromString(text)
                if r.width > 0, r.height > 0 { saved = r }
            }
            applyingFrame = true
            win.setFrame(compOpenFrame(saved: saved, size: size, screens: NSScreen.screens.map { $0.visibleFrame }), display: false)
            applyingFrame = false
        }
        win.level = pinned ? .floating : .normal
        child = web
        win.contentView = web
        front()
        return web
    }

    func front() {
        guard let win = window else { return }
        if win.isMiniaturized { win.deminiaturize(nil) }
        win.makeKeyAndOrderFront(nil)
        win.orderFrontRegardless()
    }

    /// webViewDidClose: only the current web view closes the window.
    func webViewDidClose(_ web: WKWebView) {
        if web === child { window?.close() }
    }

    /// The main window closed.
    func closeWindow() { window?.close() }

    private func saveFrame() {
        guard let w = window, !applyingFrame else { return }
        settings.set(NSStringFromRect(w.frame), forKey: Self.frameKey)
    }

    func windowDidMove(_ notification: Notification) { saveFrame() }
    func windowDidResize(_ notification: Notification) { saveFrame() }

    func windowWillClose(_ notification: Notification) {
        saveFrame()
        detailWeb?.evaluateJavaScript("compWinGone()", completionHandler: nil)
        window?.contentView = nil
        window?.delegate = nil
        window = nil
        child = nil
    }
}
