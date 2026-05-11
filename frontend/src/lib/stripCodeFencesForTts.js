/**
 * Remove fenced code blocks so Piper does not read raw code aloud.
 * Matches common ```lang newline … ``` shapes from the model.
 */
export function stripCodeFencesForTts(text) {
  if (!text) return '';
  const noBlocks = text.replace(/```[\w._+#-]*\s*\r?\n[\s\S]*?```/g, ' ');
  return noBlocks.replace(/\s+/g, ' ').trim();
}
