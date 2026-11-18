// Assertion transform for the tasks that expect a raw JSON answer.
// The assistant prompt asks for raw JSON, but models often wrap it in one Markdown fence (```json ... ```).
// That wrapper is a formatting habit, not a wrong answer, so exactly ONE fence that surrounds the whole answer
// is removed before the JSON assertions run. Anything else is left alone and still fails: prose around the
// fence, two fences, an unclosed fence. See evals/README.md.
const FENCE = /^\s*```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```\s*$/i;

function stripJsonFence(output) {
  if (typeof output !== 'string') return output;
  const match = output.match(FENCE);
  // A second fence inside the capture means two blocks, not one wrapper.
  return match && !match[1].includes('```') ? match[1] : output;
}

module.exports = stripJsonFence;
module.exports.stripJsonFence = stripJsonFence;
