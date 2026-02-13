#!/usr/bin/env node
// Eywa handoff extraction via Claude Agent SDK.
// Reads session content from stdin, outputs validated JSON to stdout.

import { query } from "@anthropic-ai/claude-agent-sdk";
import { readFileSync, mkdtempSync, rmSync, readdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { tmpdir, homedir } from "os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const systemPrompt = readFileSync(join(__dirname, "handoff.md"), "utf-8");
const schema = JSON.parse(readFileSync(join(__dirname, "handoff_schema.json"), "utf-8"));

// Model override: EYWA_CLAUDE_MODEL or EYWA_MODEL env var (default: "sonnet")
// Note: Claude Agent SDK only supports Anthropic models (sonnet, haiku, opus).
const MODEL = process.env.EYWA_CLAUDE_MODEL || process.env.EYWA_MODEL || "sonnet";

// Use temp dir as cwd so session JSONL files don't pollute project directories
const tempCwd = mkdtempSync(join(tmpdir(), "eywa-extract-"));

try {
  // Read session content from stdin
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const sessionContent = Buffer.concat(chunks).toString("utf-8");

  if (!sessionContent.trim()) {
    process.stderr.write("Error: empty stdin\n");
    process.exit(1);
  }

  let result = null;
  for await (const message of query({
    prompt: sessionContent,
    options: {
      model: MODEL,
      systemPrompt,
      allowedTools: [],
      maxTurns: 3,
      cwd: tempCwd,
      outputFormat: { type: "json_schema", schema },
    },
  })) {
    if (message.type === "result") {
      if (message.subtype === "success" && message.structured_output) {
        result = message.structured_output;
      } else {
        process.stderr.write(`Error: ${message.subtype}\n`);
        if (message.errors) process.stderr.write(message.errors.join("\n") + "\n");
        process.exit(1);
      }
    }
  }

  if (result) {
    process.stdout.write(JSON.stringify(result));
  } else {
    process.stderr.write("Error: no result received\n");
    process.exit(1);
  }
} finally {
  cleanup();
}

// Remove temp cwd and any Claude project dir it spawned
function cleanup() {
  try { rmSync(tempCwd, { recursive: true, force: true }); } catch {}
  // Claude creates ~/.claude/projects/<escaped-path>/ for the temp cwd
  const projectsDir = join(homedir(), ".claude", "projects");
  try {
    for (const entry of readdirSync(projectsDir)) {
      if (entry.includes("eywa-extract-")) {
        rmSync(join(projectsDir, entry), { recursive: true, force: true });
      }
    }
  } catch {}
}
