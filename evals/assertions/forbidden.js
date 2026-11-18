// promptfoo `javascript` assertion: the answer does not STATE a forbidden decision or piece of advice.
// A phrase inside a refusal or an "if/whether" clause is ignored (assertions/fr.js, statedForbidden).
//   config.patterns: list of regular expressions (source strings, case-insensitive, apostrophes normalised)
// Not for privacy guards: those stay strict `not-icontains`.
'use strict';
const fr = require('./fr.js');

module.exports = (output, context) => {
  const patterns = ((context && context.config) || {}).patterns;
  if (!Array.isArray(patterns) || patterns.length === 0) throw new Error('forbidden.js: config.patterns is required');
  const hits = fr.statedForbidden(String(output), patterns);
  return { pass: hits.length === 0, score: hits.length === 0 ? 1 : 0, reason: hits.length ? `states: ${hits.join(' | ')}` : 'no forbidden statement' };
};
