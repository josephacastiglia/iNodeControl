"""Update only the durable latest-result section and Gate 5 queue entry."""
from pathlib import Path

record=Path(__file__).resolve().parent
main=record.parents[1].parent/'iMouseXP-2.0'
path=main/'PROGRESS.md'
text=path.read_bytes().decode('utf-8')
newline='\r\n' if '\r\n' in text else '\n'
heading='## Latest result: C24C FKA shortcut, 11 October'
start=text.index(heading)
end=text.index(newline+'---',start)
new='''## Latest result: repeated C24C shortcut and real-console tests, 11 October

**Repeatable success inside a prepared field; persistence failed. Gate 5 remains open.** Five unique fields with matched 30-second measurement waits produced Hithere / Hi there / Hithere / Hi there / Hithere. Both shortcut conditions preserved the space; all three baselines lost it. The middle baseline was shared and counted once. No named mode message was confirmed; the operator saw a yellow highlight. Physical FKA Off → On restored the baseline between comparisons.

The unchanged `b0708e3` console's actual Send text button produced exact short text and exact 100-character text when one shortcut was applied inside that same fresh note. A separate 100-character send in a new note after physical Home/app navigation, without another shortcut, lost its first space (99/100). A planned six-character append click produced no visible change or completion entry and remains unverified; no repeat click or API substitution was sent. No character padding, remapping, changed HID timing or automatic toggle was added.

FKA On and original appearance options were visually restored. The candidate closed normally and released its lease; test kernel 11624 and receiver 42004 exited. The unchanged release restarted as kernel 10892 with receivers C24C 38684 / C241 4760. Operator recasting and installed-console restoration are pending, followed by final hash verification. C241 had no device/receiver/input path in the temporary test configuration and received no test input. No promotion, deployment or push.

Latest report: `../iMouseXP-2.0-fka-passthrough-probe/analysis/fka-pass-through-probe-20261011/REPEAT-REPORT.md`. New evidence will be sealed in `../iMouseXP-2.0-evidence-archive/20261011-fka-pass-through-repeat/` after restoration. The earlier single sequence, its unmatched waits and completed restoration remain preserved in `LIVE-REPORT.md` and `20261011-fka-pass-through-live/`. Next offline work: an explicitly controlled typing workflow that keeps the phone's mode unknown and does not infer readiness across navigation/focus changes, plus trace evidence for the uncertain append click. More live testing needs coordination. Do not repeat the completed extra-click or matched-wait comparisons as pending work.

'''
text=text[:start]+new.replace('\n',newline)+text[end:]
lines=text.splitlines(keepends=True)
indices=[i for i,line in enumerate(lines) if line.startswith('6. **Gate 5 FKA-On Typing Comparison')]
assert len(indices)==1, 'Unexpected Gate 5 queue structure'
lines[indices[0]]='6. **Gate 5 FKA Typing (REPEATS COMPLETE; PARTIAL REAL-CONSOLE SUCCESS):** The original six-note extra-click comparison lost the first space in all six notes. Exact-binary offline checks passed 60 assertions and preserved Space at the transport boundary. The separate default-disabled probe passed 123 simulated kernel tests and three invalid-startup checks. Five matched-wait fields later reproduced the shortcut/reset reversal twice (shared middle baseline). Real-console short and 100-character typing passed when the shortcut was applied inside that fresh note; a new note without another shortcut lost the space again. An append click was unverified. Mode acknowledgement, dependable focus/navigation handling and broader typing acceptance remain open. See the latest result above and `REPEAT-REPORT.md`; no automatic prefix, mapping or timing change, promotion or push. Do not repeat completed comparisons as pending work.'+newline
path.write_bytes(''.join(lines).encode('utf-8'))
print('Latest result and Gate 5 queue updated; all other progress sections preserved.')
