#!/usr/bin/env node

const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const packageMetadata = require('../package.json');

const TARGETS = ['claude', 'codex', 'gemini', 'antigravity', 'cursor', 'opencode'];
const args = process.argv.slice(2);
const command = args[0] || 'help';
const repoRoot = path.resolve(__dirname, '..');

function fail(message) {
  console.error(`\x1b[31m[error]\x1b[0m ${message}`);
  process.exit(2);
}

function optionValue(name, fallback) {
  const inline = args.find((argument) => argument.startsWith(`--${name}=`));
  if (inline) return inline.slice(name.length + 3);
  const index = args.indexOf(`--${name}`);
  if (index !== -1) {
    if (!args[index + 1] || args[index + 1].startsWith('-')) {
      fail(`--${name} requires a value`);
    }
    return args[index + 1];
  }
  return fallback;
}

function hasFlag(name) {
  return args.includes(`--${name}`);
}

function detectTargets(root) {
  return TARGETS.filter((target) => fs.existsSync(path.join(root, `.${target}`)));
}

function printHelp() {
  console.log(`\x1b[36m@indium-ai-labs/agentkit CLI v${packageMetadata.version}\x1b[0m`);
  console.log('Portable AI coding-agent skills, subagents, and templates.\n');
  console.log('Usage:');
  console.log('  agentkit install --target=<agent> [--scope=project|user] [--project-dir=<path>]');
  console.log('  agentkit add <name> --target=<agent> [--scope=project|user] [--project-dir=<path>]\n');
  console.log('Behavior:');
  console.log('  Project scope is the default and writes only inside the chosen project.');
  console.log('  User scope writes only to the selected agent directory under your home.');
  console.log('  Auto-detection uses existing agent directories and fails closed if none exist.');
  console.log('  Use --target=all only when installation into every supported agent is intended.\n');
  console.log(`Targets: ${TARGETS.join(', ')}, all`);
  console.log('Options:');
  console.log('  --scope=project|user   Installation boundary (default: project)');
  console.log('  --project-dir=<path>   Project destination (default: current directory)');
  console.log('  --target=<agent>       One target, comma-separated targets, all, or auto');
  console.log('  --mode=copy|link       Durable copies by default; links suit repository development');
  console.log('  --force                Replace existing copies of agentkit content (for upgrades)');
  console.log('  --global               Alias for --scope=user\n');
  console.log('Examples:');
  console.log('  npx @indium-ai-labs/agentkit install --target=codex');
  console.log('  npx @indium-ai-labs/agentkit add systematic-debugging --target=claude');
  console.log('  npx @indium-ai-labs/agentkit install --scope=user --target=cursor');
}

if (['help', '--help', '-h'].includes(command)) {
  printHelp();
  process.exit(0);
}
if (!['add', 'install'].includes(command)) {
  fail(`unknown command '${command}'; use --help for usage`);
}

const item = command === 'add' ? args[1] : 'all';
if (command === 'add' && (!item || item.startsWith('-'))) {
  fail('add requires one skill or subagent name');
}

const scope = hasFlag('global') ? 'user' : optionValue('scope', 'project').toLowerCase();
if (!['project', 'user'].includes(scope)) fail(`unsupported scope '${scope}'`);

const projectDir = path.resolve(optionValue('project-dir', process.cwd()));
if (scope === 'project' && !fs.existsSync(projectDir)) {
  fail(`project directory does not exist: ${projectDir}`);
}
if (scope === 'user' && optionValue('project-dir', null)) {
  fail('--project-dir cannot be used with user scope');
}

const requestedTarget = optionValue('target', 'auto').toLowerCase();
let targets;
if (requestedTarget === 'auto') {
  const detectionRoot = scope === 'project' ? projectDir : os.homedir();
  targets = detectTargets(detectionRoot);
  if (!targets.length) {
    fail(
      `No agent target was detected in ${detectionRoot}. ` +
      `Choose one with --target=${TARGETS.join('|')}, or explicitly use --target=all.`
    );
  }
} else if (requestedTarget === 'all') {
  targets = ['all'];
} else {
  targets = requestedTarget.split(',').map((target) => target.trim()).filter(Boolean);
  const unsupported = targets.find((target) => !TARGETS.includes(target));
  if (unsupported) fail(`unsupported target '${unsupported}'`);
}

const mode = optionValue('mode', 'copy').toLowerCase();
if (!['copy', 'link'].includes(mode)) fail(`unsupported mode '${mode}'`);

const installerArguments = [
  path.join(repoRoot, 'scripts', 'install.py'),
  '--scope', scope,
  '--item', item,
  '--mode', mode,
];
for (const target of targets) installerArguments.push('--target', target);
if (scope === 'project') installerArguments.push('--project-dir', projectDir);
if (command === 'install') installerArguments.push('--include-context');
if (hasFlag('force')) installerArguments.push('--force');

const pythonCommand = process.env.AGENTKIT_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
console.log(
  `\x1b[36m[agentkit]\x1b[0m ${command === 'add' ? `Adding ${item}` : 'Installing bundle'} ` +
  `to ${scope} scope for ${targets.join(', ')}...`
);
const result = spawnSync(pythonCommand, installerArguments, { stdio: 'inherit' });
if (result.error) fail(`could not start ${pythonCommand}: ${result.error.message}`);
if (result.status !== 0) process.exit(result.status || 1);
console.log(`\x1b[32m[agentkit]\x1b[0m Installation complete.`);
