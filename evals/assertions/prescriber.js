// promptfoo `javascript` assertion: the answer names the prescribing doctor in any wording the shared matcher
// recognises (assertions/fr.js, mentionsPrescriber). Used by sante-20.
'use strict';
const fr = require('./fr.js');

module.exports = (output) => {
  const ok = fr.mentionsPrescriber(String(output));
  return { pass: ok, score: ok ? 1 : 0, reason: ok ? 'names the prescribing doctor' : 'no prescribing doctor named' };
};
