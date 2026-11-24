# Every seat of a vehicle and of the vehicles it attaches (turrets), as a player meets them (2026-11-23, host on the Falcons:
# "NINE SEATS? i thought there was at most 5 ... i need to know more"). Per seat: where it is (marker), the animation, the
# prompt, its flags (a boarding seat is an enemy's jack position, not a place to ride; an invisible seat hides its rider),
# its boarding target, and the AI seat type.
# usage: python -I seats.py <map> <vehicle spec> [...]
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff
from tagfields import fields
def seats(m, S, spec, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if spec.lower() in seen: return
    seen.add(spec.lower())
    f = fields(m, S, sprdiff.find(m, spec)); pad = '   ' * depth
    n = f.get('/Seats (count)', ('count', 0))[1]
    print(f'{pad}{spec.rsplit(chr(92), 1)[-1]}: {n} seats')
    for k in range(n):
        g = lambda name: f.get(f'/Seats[{k}]/{name}', (None, ''))[1]
        flags = set(g('Flags') or ()) | set(g('Flags #2') or ())
        kind = 'BOARDING (enemy jack position)' if any('Boarding' in x for x in flags) else 'driver' if 'Driver' in flags else 'gunner' if 'Gunner' in flags else 'passenger'
        print(f"{pad}   [{k}] {kind:31s} marker {g('Seat Marker Name') or '-':16s} anim {g('Seat Animation') or '-':14s} prompt {g('Enter Seat String') or '-':24s} "
              f"boards seat {g('Boarding Seat Index')}  AI {g('AI Seat Type')}  flags {', '.join(sorted(flags)) or '-'}")
    model = f.get('/Model', ('ref', '-'))[1]
    if model and model != '-':
        mf = fields(m, S, sprdiff.find(m, model))
        kids = sorted({v[1] for k, v in mf.items() if k.endswith('/Child Object') and v[0] == 'ref' and v[1].endswith('.vehi')})
        for kid in kids: seats(m, S, kid, depth + 1, seen)
def main():
    m, S = sprdiff.load(sys.argv[1])
    for spec in sys.argv[2:]: seats(m, S, spec); print()
main()
