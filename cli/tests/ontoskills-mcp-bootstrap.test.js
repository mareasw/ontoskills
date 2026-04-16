const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");

process.env.ONTOSKILLS_HOME = path.join(os.tmpdir(), `ontoskills-home-${process.pid}`);

const cli = require("../ontoskills.js");

test("parseMcpInstallArgs defaults to global runtime-only", () => {
  const parsed = cli.parseMcpInstallArgs([]);
  assert.equal(parsed.scope, "global");
  assert.deepEqual(parsed.targets, []);
});

test("parseMcpInstallArgs supports multiple flags and project scope", () => {
  const parsed = cli.parseMcpInstallArgs(["--project", "--codex", "--cursor", "--vscode"]);
  assert.equal(parsed.scope, "project");
  assert.deepEqual(parsed.targets, ["codex", "cursor", "vscode"]);
});

test("configureMcpServersJson writes stdio server config", async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "ontoskills-cursor-"));
  const configPath = path.join(tempDir, "mcp.json");
  await cli.configureMcpServersJson(configPath, {
    name: "ontomcp",
    command: "/tmp/ontomcp",
    args: ["--flag"]
  });
  const raw = JSON.parse(await fs.readFile(configPath, "utf-8"));
  assert.deepEqual(raw, {
    mcpServers: {
      ontomcp: {
        command: "/tmp/ontomcp",
        args: ["--flag"]
      }
    }
  });
});

test("configureOpenCodeJson preserves schema and enables local server", async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "ontoskills-opencode-"));
  const configPath = path.join(tempDir, "opencode.json");
  await cli.configureOpenCodeJson(configPath, {
    name: "ontomcp",
    command: "/tmp/ontomcp",
    args: []
  });
  const raw = JSON.parse(await fs.readFile(configPath, "utf-8"));
  assert.equal(raw.$schema, "https://opencode.ai/config.json");
  assert.deepEqual(raw.mcp.ontomcp, {
    type: "local",
    command: ["/tmp/ontomcp"],
    enabled: true
  });
});

test("configureQwenJson writes mcpServers in settings.json", async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "ontoskills-qwen-"));
  const configPath = path.join(tempDir, "settings.json");
  await cli.configureQwenJson(configPath, {
    name: "ontomcp",
    command: "/tmp/ontomcp",
    args: ["--ontology-root", "/tmp/ontologies"]
  });
  const raw = JSON.parse(await fs.readFile(configPath, "utf-8"));
  assert.deepEqual(raw.mcpServers.ontomcp, {
    command: "/tmp/ontomcp",
    args: ["--ontology-root", "/tmp/ontologies"]
  });
});

test("configureCursorMcp writes project-local cursor config", async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), "ontoskills-project-"));
  const result = await cli.configureCursorMcp(
    { name: "ontomcp", command: "/tmp/ontomcp", args: [] },
    "project",
    cwd
  );
  assert.equal(result.status, "configured_by_file");
  const raw = JSON.parse(await fs.readFile(path.join(cwd, ".cursor", "mcp.json"), "utf-8"));
  assert.equal(raw.mcpServers.ontomcp.command, "/tmp/ontomcp");
});

test("configureVsCodeMcp writes project-local vscode config", async () => {
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), "ontoskills-vscode-"));
  const result = await cli.configureVsCodeMcp(
    { name: "ontomcp", command: "/tmp/ontomcp", args: [] },
    "project",
    cwd
  );
  assert.equal(result.status, "configured_by_file");
  const raw = JSON.parse(await fs.readFile(path.join(cwd, ".vscode", "mcp.json"), "utf-8"));
  assert.equal(raw.mcpServers.ontomcp.command, "/tmp/ontomcp");
});
