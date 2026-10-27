// Mini window views: Store, RootView, Header, ListView (native), DetailView (the web monitor in a WKWebView).
// The decisions (sort, filter, step text, pulse, Detail load/select) live in ListModel.swift; this file draws them.
import SwiftUI
import WebKit

enum Mode: String {
    case list, detail
}

/// Screen settings only: mode, pinned and the two frames. No task data is written anywhere.
let settings = UserDefaults(suiteName: "my-agent.monitor-menubar") ?? .standard

/// Owns the one web view so it survives switching to List and back (no reload when only the row changes).
final class DetailHost {
    let web: WKWebView
    var loadedPort: Int?
    var appliedSeq = 0

    init() {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .nonPersistent()   // the app writes nothing but its screen settings
        web = WKWebView(frame: .zero, configuration: cfg)
    }

    func sync(port: Int?, seq: Int, key: String?) {
        switch detailAction(loadedPort: loadedPort, port: port, appliedSeq: appliedSeq, seq: seq, key: key) {
        case .off:
            loadedPort = nil
        case .load(let url):
            load(url, port: port, seq: seq)
        case .select(let js):
            appliedSeq = seq
            web.evaluateJavaScript(js) { [weak self] result, error in
                // 1 means selectTask ran; 0 or an error means the page is still loading or has no such function
                if error == nil, (result as? NSNumber)?.intValue == 1 { return }
                guard let self = self, let port = port else { return }
                self.load(detailURL(port: port, key: key), port: port, seq: seq)
            }
        case .none:
            break
        }
    }

    private func load(_ url: String, port: Int?, seq: Int) {
        guard let u = URL(string: url) else { return }
        web.load(URLRequest(url: u))
        loadedPort = port
        appliedSeq = seq
    }
}

final class Store: ObservableObject {
    @Published var mode: Mode {
        didSet { settings.set(mode.rawValue, forKey: "mode") }
    }
    @Published var pinned: Bool {
        didSet { settings.set(pinned, forKey: "pinned") }
    }
    @Published var filter = ListFilter.all
    @Published var listState = ListState.off
    @Published var port: Int?
    @Published var selectedKey: String?
    @Published var selectSeq = 0
    let detail = DetailHost()

    init() {
        mode = Mode(rawValue: settings.string(forKey: "mode") ?? "") ?? .list
        pinned = settings.bool(forKey: "pinned")
    }

    /// Called from the 5 s poll with the result of the same server lookup the menu uses.
    func update(port: Int?, list: ListState) {
        if port == nil { detail.loadedPort = nil }   // server gone: load again when it comes back
        if self.port != port { self.port = port }
        if listState != list { listState = list }
    }

    func open(_ key: String) {
        selectedKey = key
        selectSeq += 1
        mode = .detail
    }
}

// MARK: colors (web palette, light/dark)

private func dynamic(_ light: (Double, Double, Double), _ dark: (Double, Double, Double)) -> Color {
    Color(nsColor: NSColor(name: nil) { ap in
        let c = ap.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light
        return NSColor(srgbRed: c.0 / 255, green: c.1 / 255, blue: c.2 / 255, alpha: 1)
    })
}

private let okColor = dynamic((0x1d, 0x7a, 0x3e), (0x5f, 0xd0, 0x8a))     // web --ok
private let runColor = dynamic((0x25, 0x52, 0xc9), (0x7e, 0xa3, 0xff))    // web --run
private let gateColor = dynamic((0xc4, 0x3d, 0x12), (0xff, 0x8a, 0x5c))   // web --gate
private let doneColor = dynamic((0x25, 0x52, 0xc9), (0x7e, 0xa3, 0xff))
private let idleColor = Color.secondary

private func markColor(_ row: TaskRow) -> Color {
    switch row.status {
    case "running": return row.waiting ? gateColor : okColor
    case "done": return doneColor
    default: return idleColor
    }
}

private func cellColor(_ c: Character) -> Color {
    switch c {
    case "d": return okColor
    case "c": return runColor
    case "s": return gateColor
    default: return Color.secondary.opacity(0.25)
    }
}

// MARK: pulse (one shared clock)

/// Web `pulse`: opacity 1 -> .3 -> 1 every 1.4 s. Computed from the wall clock, so every pulsing
/// element is in step and a list refresh does not restart it.
private func pulseOpacity(_ date: Date) -> Double {
    0.65 + 0.35 * cos(2 * Double.pi * date.timeIntervalSinceReferenceDate / 1.4)
}

private struct Pulse: ViewModifier {
    let active: Bool
    func body(content: Content) -> some View {
        if active {
            TimelineView(.animation(minimumInterval: 1.0 / 30)) { ctx in
                content.opacity(pulseOpacity(ctx.date))
            }
        } else {
            content
        }
    }
}

// MARK: views

struct RootView: View {
    @ObservedObject var store: Store

    var body: some View {
        VStack(spacing: 0) {
            Header(store: store)
            if store.mode == .list {
                ListView(store: store)
            } else {
                DetailView(store: store)
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .ignoresSafeArea(.container, edges: .top)
    }
}

/// Small segmented control like the prototype's `.seg`: 12 pt, accent fill on the selected cell.
struct Seg<T: Hashable>: View {
    let items: [(T, String)]
    @Binding var selection: T
    var fill = false

    var body: some View {
        HStack(spacing: 0) {
            ForEach(items.indices, id: \.self) { i in
                let on = items[i].0 == selection
                Text(items[i].1)
                    .font(.system(size: 12))
                    .lineLimit(1)
                    .padding(.horizontal, fill ? 4 : 9)
                    .padding(.vertical, 2)
                    .frame(maxWidth: fill ? .infinity : nil)
                    .foregroundColor(on ? .white : .secondary)
                    .background(on ? Color.accentColor : Color.clear)
                    .contentShape(Rectangle())
                    .onTapGesture { selection = items[i].0 }
            }
        }
        .background(Color(nsColor: .textBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor), lineWidth: 1))
    }
}

struct Header: View {
    @ObservedObject var store: Store

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Seg(items: [(Mode.list, "List"), (Mode.detail, "Detail")], selection: $store.mode)
                Spacer()
                Button {
                    store.pinned.toggle()
                } label: {
                    Image(systemName: store.pinned ? "pin.fill" : "pin")
                        .font(.system(size: 13))
                        .foregroundColor(store.pinned ? .accentColor : .secondary)
                }
                .buttonStyle(.plain)
                .frame(width: 16, height: 16)
                .help(store.pinned ? "Unpin" : "Keep on top")
            }
            .padding(.leading, 76)   // clear of the traffic lights
            .padding(.trailing, 10)
            .padding(.top, 8)
            .padding(.bottom, 8)
            .background(Color(nsColor: .controlBackgroundColor))
            Divider()
            if store.mode == .list {
                Seg(items: ListFilter.allCases.map { ($0, $0.rawValue.capitalized) }, selection: $store.filter, fill: true)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color(nsColor: .controlBackgroundColor))
                Divider()
            }
        }
    }
}

struct ListView: View {
    @ObservedObject var store: Store

    var body: some View {
        switch store.listState {
        case .off:
            notice("Monitor server is off")
        case .on(let all):
            let rows = filterRows(sortRows(all), store.filter)
            if rows.isEmpty {
                notice(store.filter == .all ? "No tasks" : "No \(store.filter.rawValue) tasks")
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(rows, id: \.key) { row in
                            RowView(row: row) { store.open(row.key) }
                        }
                    }
                    .transaction { $0.animation = nil }   // a refresh must not slide the rows
                }
            }
        }
    }

    private func notice(_ text: String) -> some View {
        Text(text).foregroundColor(.secondary).frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct RowView: View {
    let row: TaskRow
    let onTap: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let pulse = pulses(row) && !reduceMotion
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(statusMark(row))
                    .font(.system(size: 12.5, weight: .bold))
                    .foregroundColor(markColor(row))
                    .frame(width: 14)
                    .modifier(Pulse(active: pulse))
                Text(row.id)
                    .font(.system(size: 12.5, weight: .semibold))
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer(minLength: 0)
                Text(stepLabel(row))
                    .font(.system(size: 11.5))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: 120, alignment: .trailing)
                    .layoutPriority(1)
                Text(elapsedText(row.elapsed))
                    .font(.system(size: 11.5).monospacedDigit())
                    .foregroundColor(.secondary)
                    .frame(minWidth: 34, alignment: .trailing)
                    .layoutPriority(1)
            }
            HStack(spacing: 2) {
                ForEach(Array(railStates(row).enumerated()), id: \.offset) { _, c in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(cellColor(c))
                        .frame(height: 6)
                        .modifier(Pulse(active: pulse && c == "c"))
                }
            }
            .frame(maxWidth: 150)
            .padding(.leading, 20)   // under the task ID (14 pt mark + 6 pt gap)
            .padding(.top, 4)
        }
        .padding(.horizontal, 10)
        .padding(.top, 7)
        .padding(.bottom, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .onTapGesture(perform: onTap)
        .overlay(alignment: .bottom) { Divider() }
    }
}

struct DetailView: View {
    @ObservedObject var store: Store

    var body: some View {
        if store.port == nil {
            Text("Monitor server is off").foregroundColor(.secondary).frame(maxWidth: .infinity, maxHeight: .infinity)
                .onAppear { store.detail.sync(port: nil, seq: store.selectSeq, key: store.selectedKey) }
        } else {
            WebHost(store: store)
        }
    }
}

struct WebHost: NSViewRepresentable {
    @ObservedObject var store: Store

    func makeNSView(context: Context) -> WKWebView { store.detail.web }

    func updateNSView(_ view: WKWebView, context: Context) {
        store.detail.sync(port: store.port, seq: store.selectSeq, key: store.selectedKey)
    }
}
