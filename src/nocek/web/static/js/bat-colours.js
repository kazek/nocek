// The night's colours. The four bats a recorder hears most each get a hue of their
// own; every other named bat shares one neutral tone; recordings without a name stay
// grey. Four, because on a bar where any bat can stand beside any other, only four of
// the hues stay apart for everyone, colour-blind readers included (checked with the
// palette validator, all pairs, light and dark). The hues are --bat-1 ... --bat-4 in
// style.css. A colour follows the bat, not its rank on a night: it is fixed by the
// recorder's whole season.

export const HUES = 4;

// One named animal's taxa as a key: ["Nyctalus noctula"] -> "Nyctalus noctula".
export function keyOf(taxa) {
  return [...taxa].sort().join(",");
}

// species: the season's totals, most recorded first. Map of key -> hue number (1-4).
export function assignHues(species) {
  const sorted = [...species].sort((a, b) => b.recordings - a.recordings);
  return new Map(sorted.slice(0, HUES).map((s, i) => [keyOf(s.taxa), i + 1]));
}

// What a recording holds, as the parts its mark is drawn from, tallest first.
// kind: "bat" (key, hue or null for "other"), "withheld", "quiet" or "unanalysed".
export function partsOf(row, hues) {
  if (!row.analysed) return [{ kind: "unanalysed" }];
  if (row.sources === 0) return [{ kind: "quiet" }];
  const named = row.named.map((taxa) => {
    const key = keyOf(taxa);
    return { kind: "bat", key, taxa, hue: hues.get(key) ?? null };
  });
  const withheld = row.sources > named.length ? [{ kind: "withheld" }] : [];
  return [...named, ...withheld];
}

export function colourOf(part) {
  if (part.kind === "bat") return part.hue ? `var(--bat-${part.hue})` : "var(--bat-other)";
  return `var(--bat-${part.kind})`;
}
