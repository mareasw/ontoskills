const fs = require("fs");
const path = require("path");
const os = require("os");

const {
  BIN_DIR,
  commandExists,
  runCommandResult,
  ensureArray,
  compact,
  writeManagedJson,
} = require("./paths");

const MCP_SERVER_NAME = "ontomcp";

const MCP_CLIENT_FLAGS = new Map([
  ["--codex", "codex"],
  ["--claude", "claude"],
  ["--qwen", "qwen"],
  ["--cursor", "cursor"],
  ["--vscode", "vscode"],
  ["--windsurf", "windsurf"],
  ["--antigravity", "antigravity"],
  ["--opencode", "opencode"]
]);
const MCP_CLIENT_ORDER = ["codex", "claude", "qwen", "cursor", "vscode", "windsurf", "antigravity", "opencode"];

// --- Argument parsing ---

function parseMcpInstallArgs(args) {
  const { fail } = require("./paths");
  const targets = new Set();
  let scope = "global";
  let explicitScope = false;

  for (const arg of args) {
    if (arg === "--global") {
      if (explicitScope && scope !== "global") {
        fail("Use either --global or --project, not both");
      }
      scope = "global";
      explicitScope = true;
      continue;
    }
    if (arg === "--project") {
      if (explicitScope && scope !== "project") {
        fail("Use either --global or --project, not both");
      }
      scope = "project";
      explicitScope = true;
      continue;
    }
    if (arg === "--all-clients") {
      for (const target of MCP_CLIENT_ORDER) {
        targets.add(target);
      }
      continue;
    }
    if (MCP_CLIENT_FLAGS.has(arg)) {
      targets.add(MCP_CLIENT_FLAGS.get(arg));
      continue;
    }
    if (MCP_CLIENT_ORDER.includes(arg)) {
      targets.add(arg);
      continue;
    }
    fail(`Unknown install mcp option: ${arg}`);
  }

  return { scope, targets: [...targets] };
}

function buildStdIoServerSpec() {
  return {
    name: MCP_SERVER_NAME,
    command: path.join(BIN_DIR, "ontomcp"),
    args: []
  };
}

// --- Config path helpers ---

function cursorConfigPath(scope, cwd = process.cwd()) {
  return scope === "project" ? path.join(cwd, ".cursor", "mcp.json") : path.join(os.homedir(), ".cursor", "mcp.json");
}

function vscodeProjectConfigPath(cwd = process.cwd()) {
  return path.join(cwd, ".vscode", "mcp.json");
}

function windsurfConfigPath() {
  return path.join(os.homedir(), ".codeium", "windsurf", "mcp_config.json");
}

function opencodeConfigPath(scope, cwd = process.cwd()) {
  return scope === "project" ? path.join(cwd, "opencode.json") : path.join(os.homedir(), ".config", "opencode", "opencode.json");
}

function qwenSettingsPath(scope, cwd = process.cwd()) {
  return scope === "project" ? path.join(cwd, ".qwen", "settings.json") : path.join(os.homedir(), ".qwen", "settings.json");
}

function antigravityCandidatePaths() {
  return compact([
    process.env.ANTIGRAVITY_MCP_CONFIG,
    path.join(os.homedir(), ".antigravity", "mcp_config.json"),
    path.join(os.homedir(), ".config", "antigravity", "mcp_config.json")
  ]);
}

// --- JSON config writers ---

async function configureMcpServersJson(filePath, serverSpec) {
  await writeManagedJson(filePath, (current) => {
    const next = { ...current };
    const mcpServers = { ...(current.mcpServers || {}) };
    mcpServers[serverSpec.name] = {
      command: serverSpec.command,
      args: ensureArray(serverSpec.args)
    };
    next.mcpServers = mcpServers;
    return next;
  });
}

async function configureOpenCodeJson(filePath, serverSpec) {
  await writeManagedJson(filePath, (current) => {
    const next = { ...current };
    if (!next.$schema) {
      next.$schema = "https://opencode.ai/config.json";
    }
    const mcp = { ...(current.mcp || {}) };
    mcp[serverSpec.name] = {
      type: "local",
      command: [serverSpec.command, ...ensureArray(serverSpec.args)],
      enabled: true
    };
    next.mcp = mcp;
    return next;
  });
}

async function configureQwenJson(filePath, serverSpec) {
  await writeManagedJson(filePath, (current) => {
    const next = { ...current };
    const mcpServers = { ...(current.mcpServers || {}) };
    mcpServers[serverSpec.name] = {
      command: serverSpec.command,
      args: ensureArray(serverSpec.args)
    };
    next.mcpServers = mcpServers;
    return next;
  });
}

// --- Formatting helpers ---

function formatCommand(command, args = []) {
  return [command, ...args]
    .map((part) => (/[\s"'\\]/.test(part) ? JSON.stringify(part) : part))
    .join(" ");
}

function removeIfConfigured(command, args) {
  const result = runCommandResult(command, args);
  return result.status === 0;
}

// --- Result helpers ---

function successResult(client, scope, mode, details) {
  return { client, scope, status: mode, details };
}

function manualResult(client, scope, details) {
  return { client, scope, status: "manual_required", details };
}

function skippedResult(client, scope, details) {
  return { client, scope, status: "skipped", details };
}

function scopeLabel(scope) {
  return scope === "project" ? "project" : "global";
}

// --- Client-specific adapters ---

async function configureClaudeMcp(serverSpec, scope) {
  const cliScope = scope === "project" ? "project" : "user";
  if (!commandExists("claude")) {
    return manualResult(
      "claude",
      scope,
      `Install Claude Code and run: claude mcp add --scope ${cliScope} ${serverSpec.name} -- ${formatCommand(serverSpec.command, serverSpec.args)}`
    );
  }

  removeIfConfigured("claude", ["mcp", "remove", "--scope", cliScope, serverSpec.name]);
  const result = runCommandResult("claude", ["mcp", "add", "--scope", cliScope, serverSpec.name, "--", serverSpec.command, ...serverSpec.args]);
  if (result.status !== 0) {
    return manualResult("claude", scope, (result.stderr || result.stdout || "").trim() || "Claude Code registration failed");
  }
  return successResult("claude", scope, "configured", `Registered via claude mcp add (${cliScope})`);
}

async function configureCodexMcp(serverSpec, scope) {
  if (scope === "project") {
    return manualResult(
      "codex",
      scope,
      `Codex project-local MCP bootstrap is not automated yet. Configure ${serverSpec.name} manually for this repository using ${formatCommand(serverSpec.command, serverSpec.args)}`
    );
  }
  if (!commandExists("codex")) {
    return manualResult(
      "codex",
      scope,
      `Install Codex and run: codex mcp add ${serverSpec.name} -- ${formatCommand(serverSpec.command, serverSpec.args)}`
    );
  }

  removeIfConfigured("codex", ["mcp", "remove", serverSpec.name]);
  const result = runCommandResult("codex", ["mcp", "add", serverSpec.name, "--", serverSpec.command, ...serverSpec.args]);
  if (result.status !== 0) {
    return manualResult("codex", scope, (result.stderr || result.stdout || "").trim() || "Codex registration failed");
  }
  return successResult("codex", scope, "configured", "Registered via codex mcp add");
}

async function configureQwenMcp(serverSpec, scope, cwd = process.cwd()) {
  const configPath = qwenSettingsPath(scope, cwd);
  const cliScope = scope === "project" ? "project" : "user";
  if (commandExists("qwen")) {
    const removeArgs = compact(["mcp", "remove", scope === "project" ? "--scope" : null, scope === "project" ? "project" : null, serverSpec.name]);
    removeIfConfigured("qwen", removeArgs);
    const addArgs = compact([
      "mcp",
      "add",
      scope === "project" ? "--scope" : null,
      scope === "project" ? "project" : null,
      serverSpec.name,
      serverSpec.command,
      ...serverSpec.args
    ]);
    const result = runCommandResult("qwen", addArgs);
    if (result.status === 0) {
      return successResult("qwen", scope, "configured", `Registered via qwen mcp add (${cliScope})`);
    }
  }

  await configureQwenJson(configPath, serverSpec);
  return successResult("qwen", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureCursorMcp(serverSpec, scope, cwd = process.cwd()) {
  const configPath = cursorConfigPath(scope, cwd);
  await configureMcpServersJson(configPath, serverSpec);
  return successResult("cursor", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureVsCodeMcp(serverSpec, scope, cwd = process.cwd()) {
  if (scope === "global") {
    if (!commandExists("code")) {
      return manualResult(
        "vscode",
        scope,
        `Install VS Code CLI and run: code --add-mcp '${JSON.stringify({ name: serverSpec.name, command: serverSpec.command, args: serverSpec.args })}'`
      );
    }
    const payload = JSON.stringify({ name: serverSpec.name, command: serverSpec.command, args: serverSpec.args });
    const result = runCommandResult("code", ["--add-mcp", payload]);
    if (result.status !== 0) {
      return manualResult("vscode", scope, (result.stderr || result.stdout || "").trim() || "VS Code global registration failed");
    }
    return successResult("vscode", scope, "configured", "Registered via code --add-mcp");
  }

  const configPath = vscodeProjectConfigPath(cwd);
  await configureMcpServersJson(configPath, serverSpec);
  return successResult("vscode", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureWindsurfMcp(serverSpec, scope) {
  if (scope === "project") {
    return manualResult("windsurf", scope, "Windsurf project-local MCP bootstrap is not automated yet. Use workspace settings manually.");
  }
  const configPath = windsurfConfigPath();
  await configureMcpServersJson(configPath, serverSpec);
  return successResult("windsurf", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureOpenCodeMcp(serverSpec, scope, cwd = process.cwd()) {
  const configPath = opencodeConfigPath(scope, cwd);
  await configureOpenCodeJson(configPath, serverSpec);
  return successResult("opencode", scope, "configured_by_file", `Wrote ${configPath}`);
}

async function configureAntigravityMcp(serverSpec, scope) {
  if (scope === "project") {
    return manualResult("antigravity", scope, "Antigravity project-local MCP bootstrap is not automated yet. Add OntoMCP in the project MCP settings manually.");
  }
  for (const configPath of antigravityCandidatePaths()) {
    try {
      if (fs.existsSync(path.dirname(configPath)) || fs.existsSync(configPath)) {
        await configureMcpServersJson(configPath, serverSpec);
        return successResult("antigravity", scope, "configured_by_file", `Wrote ${configPath}`);
      }
    } catch (_error) {
      continue;
    }
  }
  return manualResult(
    "antigravity",
    scope,
    `Configure OntoMCP manually in Antigravity settings using ${formatCommand(serverSpec.command, serverSpec.args)}`
  );
}

// --- Adapter registry ---

const MCP_CLIENT_ADAPTERS = {
  codex: configureCodexMcp,
  claude: configureClaudeMcp,
  qwen: configureQwenMcp,
  cursor: configureCursorMcp,
  vscode: configureVsCodeMcp,
  windsurf: configureWindsurfMcp,
  antigravity: configureAntigravityMcp,
  opencode: configureOpenCodeMcp
};

// --- Bootstrap ---

function printMcpBootstrapSummary(results) {
  const { log } = require("./paths");
  if (!results.length) {
    return;
  }
  log(`Configured OntoMCP for ${results.length} client${results.length === 1 ? "" : "s"}:`);
  for (const result of results) {
    log(`- ${result.client} [${result.scope}] ${result.status}: ${result.details}`);
  }
}

async function installMcpBootstrap(args, cwd = process.cwd()) {
  const { installMcp } = require("./install");
  await installMcp();
  const options = parseMcpInstallArgs(args);
  if (!options.targets.length) {
    return;
  }

  const serverSpec = buildStdIoServerSpec();
  const results = [];
  for (const target of options.targets) {
    const adapter = MCP_CLIENT_ADAPTERS[target];
    if (!adapter) {
      results.push(skippedResult(target, options.scope, "No adapter available"));
      continue;
    }
    const result = await adapter(serverSpec, options.scope, cwd);
    results.push(result);
  }
  printMcpBootstrapSummary(results);
}

module.exports = {
  MCP_CLIENT_FLAGS,
  MCP_CLIENT_ORDER,
  MCP_CLIENT_ADAPTERS,
  parseMcpInstallArgs,
  buildStdIoServerSpec,
  cursorConfigPath,
  vscodeProjectConfigPath,
  windsurfConfigPath,
  opencodeConfigPath,
  qwenSettingsPath,
  antigravityCandidatePaths,
  configureMcpServersJson,
  configureOpenCodeJson,
  configureQwenJson,
  formatCommand,
  removeIfConfigured,
  successResult,
  manualResult,
  skippedResult,
  scopeLabel,
  configureClaudeMcp,
  configureCodexMcp,
  configureQwenMcp,
  configureCursorMcp,
  configureVsCodeMcp,
  configureWindsurfMcp,
  configureOpenCodeMcp,
  configureAntigravityMcp,
  printMcpBootstrapSummary,
  installMcpBootstrap,
};
