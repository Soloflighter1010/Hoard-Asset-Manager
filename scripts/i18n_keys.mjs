// Parse translation calls with Acorn. Conditions, comments and argument values are
// never translation keys; only possible values of the first argument are returned.
import { parse } from 'acorn';
import { parse as parseSvelte } from 'svelte/compiler';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Walk syntax nodes, ignoring source locations and other scalar metadata.
function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  if (node.type) visit(node);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(child => walk(child, visit));
    else if (value && typeof value === 'object') walk(value, visit);
  }
}

// Enumerate statically knowable results, without visiting a conditional's test.
function strings(node) {
  if (!node) return [];
  if (node.type === 'Literal') return typeof node.value === 'string' ? [node.value] : [];
  if (node.type === 'TemplateLiteral' && !node.expressions.length) return [node.quasis[0].value.cooked];
  if (node.type === 'ConditionalExpression') return [...strings(node.consequent), ...strings(node.alternate)];
  if (node.type === 'LogicalExpression') return [...strings(node.left), ...strings(node.right)];
  if (node.type === 'BinaryExpression' && node.operator === '+') {
    return strings(node.left).flatMap(a => strings(node.right).map(b => a + b));
  }
  if (node.type === 'SequenceExpression') return strings(node.expressions.at(-1));
  return [];
}

// Return source locations too: they make changed English messages diagnosable.
export function collect(source, filename = '<script>') {
  const ast = filename.endsWith('.svelte') ? parseSvelte(source, { modern: true })
    : parse(source, { ecmaVersion: 'latest', sourceType: 'script', locations: true });
  const calls = [];
  walk(ast, node => {
    if (node.type !== 'CallExpression' || node.callee.type !== 'Identifier' ||
        !['tr', 'trHTML'].includes(node.callee.name)) return;
    for (const value of strings(node.arguments[0])) {
      const key = value.replace(/\s+/gu, ' ').trim();
      if (key) calls.push({ key, file: filename, line: node.loc?.start.line ?? source.slice(0, node.start).split("\n").length });
    }
  });
  return calls;
}

// The Python caller extracts executable inline scripts with HTMLParser, not regex.
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const inputs = JSON.parse(readFileSync(0, 'utf8'));
  process.stdout.write(JSON.stringify(inputs.flatMap(({ source, file }) => collect(source, file))));
}
