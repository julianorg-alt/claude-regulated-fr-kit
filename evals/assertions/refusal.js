// promptfoo `javascript` assertion: the answer refuses, says the information is absent, or says the service is
// not competent, in any wording the shared matcher recognises (assertions/fr.js).
//   config.kind:  "refusal" (default) | "absent" | "competence"
//   config.also:  optional list of plain substrings that are also accepted (task-specific wording, e.g. "relève")
'use strict';
const fr = require('./fr.js');

const KINDS = { refusal: fr.isRefusal, absent: fr.isAbsentInfo, competence: fr.isNotCompetent };

module.exports = (output, context) => {
  const config = (context && context.config) || {};
  const kind = config.kind || 'refusal';
  const matcher = KINDS[kind];
  if (!matcher) throw new Error(`refusal.js: unknown kind ${kind}`);
  const text = String(output);
  const lowered = fr.norm(text);
  const ok = matcher(text) || (config.also || []).some((s) => lowered.includes(fr.norm(s)));
  return { pass: ok, score: ok ? 1 : 0, reason: ok ? `matches ${kind}` : `no ${kind} wording found` };
};
