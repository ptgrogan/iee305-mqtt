// Profanity filter for the browser client. It only changes what this page shows and
// sends: the broker still delivers every message, and the Python scripts print them
// unfiltered. Edit BLOCKED_WORDS to tune it; changes take effect on the next page load.
"use strict";

// Lowercase letters only. A word matches as a whole word; * matches any letters, so
// "fuck*" also matches "fucking" and "*fuck*" matches "motherfucker". Each letter
// may repeat ("fuuuck"), and common substitutions such as "sh1t" and "a$$" count.
// Whole-word matching keeps innocent words such as "class" and "assess" visible.
const BLOCKED_WORDS = [
  // Profanity and sexual terms
  "*fuck*", "*shit*", "ass", "*asshole*", "jackass", "dumbass", "*bitch*", "bastard*",
  "cunt*", "dick", "dicks", "dickhead*", "cock", "cocks", "cocksuck*", "puss", "pussy",
  "pussies", "piss*", "twat*", "wank*", "slut*", "whore*", "tits", "titty", "titties",
  "boobs", "boobies", "penis*", "vagina*", "*porn*", "dildo*", "cum", "cumshot*",
  "jizz*", "blowjob*", "handjob*", "horny", "rape", "raped", "rapes", "rapist*",
  "stfu", "kys",
  // Slurs
  "nigger*", "nigga*", "chink*", "gook*", "spic", "spics", "wetback*", "kike*",
  "beaner*", "coon", "coons", "raghead*", "towelhead*", "paki", "pakis", "tranny",
  "trannies", "faggot*", "fag", "fags", "dyke*", "retard", "retards", "retarded",
];
// Innocent words that the patterns above would otherwise hide.
const ALLOWED_WORDS = ["shiitake", "shiitakes"];

const BLOCKED = new RegExp(`^(?:${BLOCKED_WORDS.map((entry) =>
  [...entry].map((letter) => letter === "*" ? ".*" : `${letter}+`).join("")).join("|")})$`, "u");
const SUBSTITUTES = { 0: "o", 1: "i", 3: "e", 4: "a", 5: "s", 7: "t", "@": "a", $: "s", "!": "i" };
const WORD = /[\p{L}\p{N}@$!]+/gu;
// Single characters separated by spaces or dots, as in "f u c k" or "f.u.c.k".
const SPACED = /(?<![\p{L}\p{N}@$])(?:[\p{L}\p{N}@$][ ._-]){2,}[\p{L}\p{N}@$](?![\p{L}\p{N}@$])/gu;

function blocked(word) {
  word = word.toLowerCase().normalize("NFKD").replace(/\p{M}/gu, "")  // strip accents
             .replace(/^!+|!+$/g, "");                                // "shit!" is "shit"
  // Read digits as letters only inside words, so a number such as 455 stays a number.
  if (/\p{L}/u.test(word)) word = word.replace(/[0-9@$!]/g, (c) => SUBSTITUTES[c] ?? c);
  return BLOCKED.test(word) && !ALLOWED_WORDS.includes(word);
}

// Replace each blocked word with asterisks of the same length.
function clean(text) {
  const mask = (span) => span.replace(/\S/g, "*");
  return String(text)
    .replace(SPACED, (span) => blocked(span.replace(/[ ._-]/g, "")) ? mask(span) : span)
    .replace(WORD, (word) => blocked(word) ? mask(word) : word);
}
