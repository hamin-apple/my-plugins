// Pure menu logic (Foundation only, no AppKit): parse /api/tasks, build menu items and the commands they run.
// Used by the menu bar UI (main.swift) and by --print-menu, so the printed commands are the ones really run.
import Foundation

// Duplicate of STEP_NAME in web/index.html; change both together.
let stepNames: [Int: String] = [
    1: "Intake", 2: "Explore → Scope", 3: "Plan", 4: "Plan Review → G1b",
    5: "Execute", 6: "Merge · Self-check", 7: "Verify", 8: "Review → Deliver",
]

struct RunningTask: Equatable {
    let id: String
    let key: String
    let step: Int?
}

enum MenuState: Equatable {
    case off
    case on([RunningTask])
}

enum ItemKind: Equatable {
    case task, info, separator, open, browser, quit
}

struct BrowserChoice: Equatable {
    let value: String
    let title: String
    let selected: Bool
    let argv: [String]
}

struct MenuItem: Equatable {
    let kind: ItemKind
    let title: String
    let key: String?
    let enabled: Bool
    let argv: [String]?
    var choices: [BrowserChoice] = []
}

// Same values as BROWSERS in monitor/opener.py.
let browserChoices: [(value: String, title: String)] = [
    ("default", "Default Browser"), ("safari", "Safari"), ("chrome", "Chrome (App Window)"),
]

enum Launch {
    case open
    case task(String)
    case start
    case setBrowser(String)
}

/// The one place that builds the monitor-up.py command line.
func command(_ launch: Launch, python: String, root: String) -> [String] {
    let script = root + "/monitor-up.py"
    switch launch {
    case .open: return [python, script, "--open"]
    case .task(let key): return [python, script, "--open", "--task", key]
    case .start: return [python, script, "--no-open"]
    case .setBrowser(let value): return [python, script, "set-browser", value]
    }
}

func parseRunning(_ data: Data) -> [RunningTask]? {
    guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let tasks = obj["tasks"] as? [[String: Any]] else { return nil }
    return tasks.compactMap { t in
        guard (t["status"] as? String) == "running",
              let id = t["id"] as? String, let key = t["key"] as? String else { return nil }
        return RunningTask(id: id, key: key, step: t["step"] as? Int)
    }
}

func taskTitle(_ t: RunningTask) -> String {
    guard let n = t.step else { return "\(t.id) · –" }
    guard let name = stepNames[n] else { return "\(t.id) · \(n)" }
    return "\(t.id) · \(n). \(name)"
}

func iconText(_ state: MenuState) -> String {
    switch state {
    case .off: return "off"
    case .on(let tasks): return String(tasks.count)
    }
}

/// The `browser` key of monitor-config.json; missing, broken or unknown means "default".
func readBrowser(env: [String: String]) -> String {
    let dir = env["MA_TASKS_DIR"].flatMap { $0.isEmpty ? nil : $0 }
        ?? (NSHomeDirectory() + "/dev/agent-tasks")
    guard let data = FileManager.default.contents(atPath: dir + "/monitor-config.json"),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let value = obj["browser"] as? String, browserChoices.contains(where: { $0.value == value }) else { return "default" }
    return value
}

func menuItems(_ state: MenuState, browser: String = "default", python: String, root: String) -> [MenuItem] {
    var items: [MenuItem] = []
    switch state {
    case .off:
        items.append(MenuItem(kind: .info, title: "Monitor server is off", key: nil, enabled: false, argv: nil))
    case .on(let tasks) where tasks.isEmpty:
        items.append(MenuItem(kind: .info, title: "No running tasks", key: nil, enabled: false, argv: nil))
    case .on(let tasks):
        for t in tasks {
            items.append(MenuItem(kind: .task, title: taskTitle(t), key: t.key, enabled: true,
                                  argv: command(.task(t.key), python: python, root: root)))
        }
    }
    items.append(MenuItem(kind: .separator, title: "", key: nil, enabled: false, argv: nil))
    items.append(MenuItem(kind: .open, title: "Open Monitor", key: nil, enabled: true,
                          argv: command(.open, python: python, root: root)))
    items.append(MenuItem(kind: .browser, title: "Browser", key: nil, enabled: true, argv: nil,
                          choices: browserChoices.map {
                              BrowserChoice(value: $0.value, title: $0.title, selected: $0.value == browser,
                                            argv: command(.setBrowser($0.value), python: python, root: root))
                          }))
    items.append(MenuItem(kind: .quit, title: "Quit", key: nil, enabled: true, argv: nil))
    return items
}

func renderMenu(_ state: MenuState, browser: String = "default", python: String, root: String) -> String {
    var lines = ["icon: " + iconText(state)]
    for item in menuItems(state, browser: browser, python: python, root: root) {
        switch item.kind {
        case .separator: lines.append("---")
        case .task:
            lines.append([item.title, item.key ?? "", "run: " + (item.argv ?? []).joined(separator: " ")].joined(separator: "\t"))
        case .open:
            lines.append(item.title + "\trun: " + (item.argv ?? []).joined(separator: " "))
        case .browser:
            // "Browser: *default safari chrome<TAB>run: <python> <root>/monitor-up.py set-browser" (the value is appended when run)
            let names = item.choices.map { ($0.selected ? "*" : "") + $0.value }.joined(separator: " ")
            let base = (item.choices.first?.argv.dropLast() ?? []).joined(separator: " ")
            lines.append(item.title + ": " + names + "\trun: " + base)
        default: lines.append(item.title)
        }
    }
    lines.append("launch: " + command(.start, python: python, root: root).joined(separator: " "))
    return lines.joined(separator: "\n")
}

// MARK: server discovery (blocking, 1 s timeout per request)

func fetch(_ port: Int, _ path: String) -> Data? {
    guard let url = URL(string: "http://127.0.0.1:\(port)\(path)") else { return nil }
    var req = URLRequest(url: url)
    req.timeoutInterval = 1
    let cfg = URLSessionConfiguration.ephemeral
    cfg.timeoutIntervalForRequest = 1
    cfg.timeoutIntervalForResource = 1
    let session = URLSession(configuration: cfg)
    defer { session.finishTasksAndInvalidate() }
    let sem = DispatchSemaphore(value: 0)
    var out: Data?
    session.dataTask(with: req) { data, resp, _ in
        if let http = resp as? HTTPURLResponse, http.statusCode == 200 { out = data }
        sem.signal()
    }.resume()
    _ = sem.wait(timeout: .now() + 2)
    return out
}

func isMonitor(_ port: Int) -> Bool {
    guard let data = fetch(port, "/api/health"),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
    return (obj["app"] as? String) == "my-agent-monitor"
}

func statePort(env: [String: String]) -> Int? {
    let dir = env["MA_TASKS_DIR"].flatMap { $0.isEmpty ? nil : $0 }
        ?? (NSHomeDirectory() + "/dev/agent-tasks")
    guard let data = FileManager.default.contents(atPath: dir + "/monitor.json"),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    return obj["port"] as? Int
}

func parsePorts(_ text: String) -> ClosedRange<Int>? {
    let parts = text.split(separator: "-")
    guard parts.count == 2, let a = Int(parts[0]), let b = Int(parts[1]), a <= b else { return nil }
    return a...b
}

/// The first monitor (monitor.json port, then the range) whose /api/tasks parses.
func queryTasks(ports: ClosedRange<Int>, env: [String: String]) -> (port: Int, data: Data)? {
    var candidates: [Int] = []
    if let p = statePort(env: env) { candidates.append(p) }
    candidates += ports.filter { !candidates.contains($0) }
    for port in candidates where isMonitor(port) {
        if let data = fetch(port, "/api/tasks"), parseRunning(data) != nil { return (port, data) }
    }
    return nil
}

func queryState(ports: ClosedRange<Int>, env: [String: String]) -> MenuState {
    guard let found = queryTasks(ports: ports, env: env), let tasks = parseRunning(found.data) else { return .off }
    return .on(tasks)
}
