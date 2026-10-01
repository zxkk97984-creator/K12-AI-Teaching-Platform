export function narrationVoiceId(voice: SpeechSynthesisVoice) {
  return JSON.stringify([voice.voiceURI ?? "", voice.lang, voice.name ?? ""]);
}

function language(voice: SpeechSynthesisVoice) { return voice.lang.toLowerCase().replaceAll("_", "-"); }
export function isCantoneseVoice(voice: SpeechSynthesisVoice) {
  const lang = language(voice);
  return lang.startsWith("yue") || /^zh-(hk|mo)(-|$)/.test(lang) || /cantonese|粤语|粵語/i.test(voice.name ?? "");
}
export function isMandarinVoice(voice: SpeechSynthesisVoice) {
  if (isCantoneseVoice(voice)) return false;
  return /^cmn(-|$)|^zh-(cn|sg|tw|hans|hant)(-|$)/.test(language(voice));
}
export function narrationVoiceGroup(voice: SpeechSynthesisVoice) {
  return isMandarinVoice(voice) ? "普通话" : isCantoneseVoice(voice) ? "粤语" : "其他声音";
}
export function narrationVoiceLabel(voice: SpeechSynthesisVoice) {
  return `${voice.name || "浏览器声音"} · ${voice.lang}`;
}
export function chooseNarrationVoice(voices: SpeechSynthesisVoice[], preferredId: string) {
  const selected = preferredId ? voices.find(voice => narrationVoiceId(voice) === preferredId) : undefined;
  const mandarin = voices.filter(isMandarinVoice);
  const mainland = mandarin.filter(voice => /(^zh-cn($|-)|-cn$)/.test(language(voice)));
  const candidates = mainland.length ? mainland : mandarin;
  return { voice: selected ?? candidates.find(voice => voice.default) ?? candidates[0], missingSelection: Boolean(preferredId && !selected) };
}
