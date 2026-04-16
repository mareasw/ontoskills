const fs = require("fs");
const fsp = require("fs/promises");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

// --- Directory constants ---

const HOME_ROOT = process.env.ONTOSKILLS_HOME || process.env.ONTOSKILL_HOME || path.join(os.homedir(), ".ontoskills");
const BIN_DIR = path.join(HOME_ROOT, "bin");
const ONTOLOGY_DIR = path.join(HOME_ROOT, "ontologies");
const ONTOLOGY_AUTHOR_DIR = path.join(ONTOLOGY_DIR, "author");
const SKILLS_DIR = path.join(HOME_ROOT, "skills");
const SKILLS_AUTHOR_DIR = path.join(SKILLS_DIR, "author");
const STATE_DIR = path.join(HOME_ROOT, "state");
const CORE_DIR = path.join(HOME_ROOT, "core");
const CACHE_DIR = path.join(STATE_DIR, "cache");
const SYSTEM_DIR = path.join(ONTOLOGY_DIR, "system");
const EMBEDDINGS_DIR = path.join(SYSTEM_DIR, "embeddings");

// --- File paths ---

const REGISTRY_SOURCES_PATH = path.join(STATE_DIR, "registry.sources.json");
const REGISTRY_LOCK_PATH = path.join(STATE_DIR, "registry.lock.json");
const RELEASE_LOCK_PATH = path.join(STATE_DIR, "release.lock.json");
const CONFIG_PATH = path.join(STATE_DIR, "config.json");
const ENABLED_INDEX_PATH = path.join(SYSTEM_DIR, "index.enabled.ttl");
const CORE_ONTOLOGY_PATH = path.join(ONTOLOGY_DIR, "core.ttl");
const CORE_ONTOLOGY_URL = "https://ontoskills.sh/ontology/core.ttl";

// --- Defaults ---

const DEFAULT_REPOSITORY =
  process.env.ONTOSKILLS_RELEASE_REPO ||
  process.env.ONTOSKILL_RELEASE_REPO ||
  "mareasw/ontoskills";
const DEFAULT_REGISTRY_URL =
  process.env.ONTOSKILLS_REGISTRY_URL ||
  process.env.ONTOSKILL_REGISTRY_URL ||
  "https://raw.githubusercontent.com/mareasw/ontostore/main/index.json";

// --- Logging ---

function log(message) {
  process.stdout.write(`${message}\n`);
}

function fail(message, code = 1) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

function warn(message) {
  process.stderr.write(`${message}\n`);
}

// --- Filesystem utilities ---

async function ensureLayout() {
  for (const target of [BIN_DIR, ONTOLOGY_DIR, ONTOLOGY_AUTHOR_DIR, SKILLS_DIR, SKILLS_AUTHOR_DIR, STATE_DIR, CORE_DIR, CACHE_DIR, SYSTEM_DIR, EMBEDDINGS_DIR]) {
    await fsp.mkdir(target, { recursive: true });
  }
}

async function readJson(filePath, fallback) {
  try {
    const raw = await fsp.readFile(filePath, "utf-8");
    return JSON.parse(raw);
  } catch (error) {
    if (fallback !== undefined) {
      return fallback;
    }
    throw error;
  }
}

async function writeJson(filePath, value) {
  await fsp.mkdir(path.dirname(filePath), { recursive: true });
  await fsp.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}

async function readJsonFile(filePath, fallback = {}) {
  try {
    const raw = await fsp.readFile(filePath, "utf-8");
    return raw.trim() ? JSON.parse(raw) : fallback;
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return fallback;
    }
    throw error;
  }
}

async function writeManagedJson(filePath, mutator) {
  const current = await readJsonFile(filePath, {});
  const next = mutator(current) || current;
  await writeJson(filePath, next);
}

// --- Command execution ---

function commandExists(command) {
  const result = spawnSync(command, ["--help"], { stdio: "ignore" });
  return result.status === 0;
}

function runCommandResult(command, args, options = {}) {
  return spawnSync(command, args, { stdio: "pipe", encoding: "utf-8", ...options });
}

function runCommand(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: "pipe", encoding: "utf-8", ...options });
  if (result.status !== 0) {
    fail(`${command} ${args.join(" ")} failed:\n${result.stderr || result.stdout}`);
  }
  return result;
}

// --- Misc utilities ---

function compact(value) {
  return value.filter(Boolean);
}

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "imported";
}

// --- Exports ---

module.exports = {
  // Paths
  HOME_ROOT,
  BIN_DIR,
  ONTOLOGY_DIR,
  ONTOLOGY_AUTHOR_DIR,
  SKILLS_DIR,
  SKILLS_AUTHOR_DIR,
  STATE_DIR,
  CORE_DIR,
  CACHE_DIR,
  SYSTEM_DIR,
  EMBEDDINGS_DIR,
  REGISTRY_SOURCES_PATH,
  REGISTRY_LOCK_PATH,
  RELEASE_LOCK_PATH,
  CONFIG_PATH,
  ENABLED_INDEX_PATH,
  CORE_ONTOLOGY_PATH,
  CORE_ONTOLOGY_URL,
  DEFAULT_REPOSITORY,
  DEFAULT_REGISTRY_URL,
  // Logging
  log,
  fail,
  warn,
  // Filesystem
  ensureLayout,
  readJson,
  writeJson,
  readJsonFile,
  writeManagedJson,
  // Commands
  commandExists,
  runCommandResult,
  runCommand,
  // Utilities
  compact,
  ensureArray,
  slugify,
};
