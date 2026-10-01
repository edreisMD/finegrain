import AppKit
import Foundation

struct Settings: Decodable {
    let python: String
    let config: String
    let workspace: String
    let companyURL: String
    let brainFolder: String
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var item: NSStatusItem!
    private var worker: Process?
    private var timer: Timer?
    private var settings: Settings?
    private var logHandle: FileHandle?
    private var state = "Setup needed"

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        let path = ProcessInfo.processInfo.environment["GM_NIGHTLY_APP_SETTINGS"] ?? (NSHomeDirectory() + "/Library/Application Support/GM Nightly Loop/app.json")
        if let data = try? Data(contentsOf: URL(fileURLWithPath: path)) {
            settings = try? JSONDecoder().decode(Settings.self, from: data)
        }
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = NSImage(systemSymbolName: "leaf.circle.fill", accessibilityDescription: "GM Nightly Loop")
        item.button?.toolTip = "GM Nightly Loop · Personal memory, company learning"
        if settings != nil { startWorker() }
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.refresh() }
    }

    private func startWorker() {
        guard let s = settings, worker?.isRunning != true else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: s.python)
        process.arguments = ["-m", "gm_nightly", "--config", s.config, "employee", "watch"]
        process.currentDirectoryURL = URL(fileURLWithPath: s.config).deletingLastPathComponent()
        try? FileManager.default.createDirectory(atPath: s.workspace, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let log = s.workspace + "/menubar-worker.log"
        if !FileManager.default.fileExists(atPath: log) { FileManager.default.createFile(atPath: log, contents: nil, attributes: [.posixPermissions: 0o600]) }
        logHandle = FileHandle(forWritingAtPath: log)
        logHandle?.seekToEndOfFile()
        process.standardOutput = logHandle
        process.standardError = logHandle
        // GUI apps do not inherit shell PATH. Onboarding stores the Gbrain executable as an absolute path.
        do { try process.run(); worker = process; state = "Starting…" }
        catch { state = "Could not start worker" }
    }

    private func entry(_ title: String, _ selector: Selector? = nil) -> NSMenuItem {
        let row = NSMenuItem(title: title, action: selector, keyEquivalent: "")
        row.target = self
        return row
    }

    private func refresh() {
        let menu = NSMenu()
        menu.addItem(entry("GM Nightly Loop"))
        if let s = settings {
            let paused = FileManager.default.fileExists(atPath: s.workspace + "/paused")
            var info: [String: Any] = [:]
            if let data = try? Data(contentsOf: URL(fileURLWithPath: s.workspace + "/status.json")), let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { info = json }
            let status = (info["state"] as? String) ?? state
            menu.addItem(entry(paused ? "Paused" : status.capitalized))
            if let relay = info["last_delivery"] as? [String: Any], let count = relay["shared_pages"] as? Int { menu.addItem(entry("\(count) compiled notes shared")) }
            if status == "error" { menu.addItem(entry("Connection needs attention")) }
            if worker?.isRunning != true { menu.addItem(entry("Restart worker", #selector(restart))) }
            menu.addItem(NSMenuItem.separator())
            menu.addItem(entry(paused ? "Resume capture & relay" : "Pause capture & relay", #selector(togglePause)))
            menu.addItem(entry("Open company Gbrain…", #selector(openCompany)))
            menu.addItem(entry("Open personal Gbrain files…", #selector(openBrain)))
            menu.addItem(entry("View GM Nightly Loop status…", #selector(openStatus)))
            menu.addItem(entry("Settings…", #selector(openSettings)))
        } else {
            menu.addItem(entry("Connect your personal and company Gbrain", #selector(showSetup)))
        }
        menu.addItem(NSMenuItem.separator())
        menu.addItem(entry("About GM Nightly Loop", #selector(about)))
        menu.addItem(entry("Quit GM Nightly Loop", #selector(quit)))
        item.menu = menu
    }

    @objc private func togglePause() {
        guard let s = settings else { return }
        let path = s.workspace + "/paused"
        if FileManager.default.fileExists(atPath: path) { try? FileManager.default.removeItem(atPath: path) }
        else { FileManager.default.createFile(atPath: path, contents: Data(), attributes: [.posixPermissions: 0o600]) }
        refresh()
    }
    @objc private func restart() { startWorker(); refresh() }
    @objc private func openCompany() { if let s = settings, let url = URL(string: s.companyURL + "/admin/") { NSWorkspace.shared.open(url) } }
    @objc private func openBrain() { if let s = settings { NSWorkspace.shared.open(URL(fileURLWithPath: s.brainFolder)) } }
    @objc private func openStatus() { if let s = settings { NSWorkspace.shared.open(URL(fileURLWithPath: s.workspace + "/status.json")) } }
    @objc private func openSettings() { if let s = settings { NSWorkspace.shared.open(URL(fileURLWithPath: s.config)) } }
    @objc private func showSetup() {
        let alert = NSAlert()
        alert.messageText = "Connect GM Nightly Loop"
        alert.informativeText = "In your GM Nightly Loop checkout, run:\n\n./scripts/install-employee.sh\n\nThe terminal setup reuses your personal Gbrain and connects the scoped company credentials your administrator provided. Then reopen this app."
        alert.addButton(withTitle: "Got it")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }
    @objc private func about() {
        let alert = NSAlert()
        alert.messageText = "GM Nightly Loop"
        alert.informativeText = "Personal Gbrain → company Gbrain → River\n\nYour agents keep their normal session files. Only selected compiled notes are shared. Gbrain owns memory and permissions; GM Nightly Loop builds datasets and evaluates new models.\n\nOpen source · Version 0.1.0"
        alert.runModal()
    }
    @objc private func quit() { worker?.terminate(); NSApp.terminate(nil) }
    func applicationWillTerminate(_ notification: Notification) { worker?.terminate(); try? logHandle?.close() }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
