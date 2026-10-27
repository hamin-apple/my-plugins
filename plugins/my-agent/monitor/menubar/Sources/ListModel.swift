// Pure List/Detail logic (Foundation only, no AppKit/SwiftUI/WebKit): rows, sort, filter, step display,
// window fitting and the Detail view's load/select decision. Used by the mini window and by
// --print-list, --fit-frame and --print-detail, so the tests see the logic the window really runs.
import Foundation

struct TaskRow: Equatable {
    let id: String
    let key: String
    let status: String?
    let waiting: Bool
    let step: Int?
    let elapsed: Int?
}

enum ListFilter: String, CaseIterable {
    case all, running, done, stopped
}

enum ListState: Equatable {
    case off
    case on([TaskRow])
}

/// Every task of /api/tasks; a task with no status or a failed read stays a row when it has id and key.
func parseTasks(_ data: Data) -> [TaskRow]? {
    guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let tasks = obj["tasks"] as? [[String: Any]] else { return nil }
    return tasks.compactMap { t in
        guard let id = t["id"] as? String, let key = t["key"] as? String else { return nil }
        return TaskRow(id: id, key: key, status: t["status"] as? String, waiting: (t["waiting"] as? Bool) ?? false,
                       step: t["step"] as? Int, elapsed: t["elapsed"] as? Int)
    }
}

/// Running (including waiting) first; inside each group the server order (newest first) stays.
func sortRows(_ rows: [TaskRow]) -> [TaskRow] {
    rows.filter { $0.status == "running" } + rows.filter { $0.status != "running" }
}

/// Same as the web filter: exact status match, so a task without status shows only under All.
func filterRows(_ rows: [TaskRow], _ filter: ListFilter) -> [TaskRow] {
    filter == .all ? rows : rows.filter { $0.status == filter.rawValue }
}

/// Follows statusBadge/ic in web/index.html.
func statusMark(_ row: TaskRow) -> String {
    switch row.status {
    case "running": return row.waiting ? "?" : "●"
    case "done": return "✓"
    default: return "■"
    }
}

func stepLabel(_ row: TaskRow) -> String {
    if row.status == "done" { return "Done" }
    guard let n = row.step else { return "–" }
    guard let name = stepNames[n] else { return "\(n)" }
    return "\(n). \(name)"
}

/// Eight cells like stepState in web/index.html: d done, c current, s stopped, - todo.
func railStates(_ row: TaskRow) -> [Character] {
    (1...8).map { n in
        if row.status == "done" { return "d" }
        guard let step = row.step else { return "-" }
        if n < step { return "d" }
        if n == step { return row.status == "stopped" ? "s" : "c" }
        return "-"
    }
}

/// Running and waiting rows pulse (the web `.dot.run`). Decided by status, not by the rail:
/// a task without status but with a step has a current cell and must not pulse.
/// Reduce Motion is not looked at here; the view does that.
func pulses(_ row: TaskRow) -> Bool {
    row.status == "running"
}

func elapsedText(_ minutes: Int?) -> String {
    guard let m = minutes else { return "–" }
    if m < 60 { return "\(m)m" }
    if m < 1440 { return "\(m / 60)h \(m % 60)m" }
    return "\(m / 1440)d \((m % 1440) / 60)h"
}

// MARK: window fitting

/// Moves a saved frame onto a visible screen: the screen it overlaps most (none: the first),
/// shrunk to the screen size and shifted fully inside. Screens are visibleFrames.
func fitFrame(_ frame: CGRect, screens: [CGRect]) -> CGRect {
    guard let first = screens.first else { return frame }
    var best = first
    var bestArea: CGFloat = 0
    for s in screens {
        let i = frame.intersection(s)
        let area = i.isNull ? 0 : i.width * i.height
        if area > bestArea { best = s; bestArea = area }
    }
    let w = min(frame.width, best.width)
    let h = min(frame.height, best.height)
    let x = min(max(frame.minX, best.minX), best.maxX - w)
    let y = min(max(frame.minY, best.minY), best.maxY - h)
    return CGRect(x: x, y: y, width: w, height: h)
}

// MARK: Detail (the web monitor in a web view)

/// Value after `#task=`. Only letters, digits and `-._~` stay; same as Python quote(key, safe='').
func taskFragment(_ key: String) -> String {
    let keep = Set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~".utf8)
    var out = ""
    for b in key.utf8 {
        if keep.contains(b) { out.append(Character(UnicodeScalar(b))) } else { out += String(format: "%%%02X", b) }
    }
    return out
}

func detailURL(port: Int, key: String?) -> String {
    var url = "http://127.0.0.1:\(port)/"
    if let key = key, !key.isEmpty { url += "#task=" + taskFragment(key) }
    return url
}

/// selectTask in web/index.html is async, so the expression ends in 1 or 0 instead of the Promise.
func selectTaskJS(_ key: String) -> String {
    let enc = JSONEncoder()
    enc.outputFormatting = [.withoutEscapingSlashes]
    let lit = (try? enc.encode(key)).flatMap { String(data: $0, encoding: .utf8) } ?? "\"\""
    return "typeof selectTask==='function'?(selectTask(\(lit)),1):0"
}

enum DetailAction: Equatable {
    case off
    case load(String)
    case select(String)
    case none
}

/// What the Detail view does now. `seq` grows on every row click, so clicking the same row again selects again.
func detailAction(loadedPort: Int?, port: Int?, appliedSeq: Int, seq: Int, key: String?) -> DetailAction {
    guard let port = port else { return .off }
    if loadedPort != port { return .load(detailURL(port: port, key: key)) }
    if seq != appliedSeq, let key = key, !key.isEmpty { return .select(selectTaskJS(key)) }
    return .none
}

// MARK: text output for --print-list

func renderList(_ state: ListState, filter: ListFilter) -> String {
    switch state {
    case .off:
        return "list: off\nMonitor server is off"
    case .on(let all):
        let rows = filterRows(sortRows(all), filter)
        if rows.isEmpty {
            return "list: 0\n" + (filter == .all ? "No tasks" : "No \(filter.rawValue) tasks")
        }
        var lines = ["list: \(rows.count)"]
        for r in rows {
            lines.append([statusMark(r), r.id, stepLabel(r), elapsedText(r.elapsed), String(railStates(r)),
                          pulses(r) ? "pulse" : "-", r.key].joined(separator: "\t"))
        }
        return lines.joined(separator: "\n")
    }
}
