"""Operator's command line for the review queue, the run plan and the slot runner. Only `run`
touches a phone (through the window tools, see farm_schedule_runner.py); nothing here posts.

  python tools/farm_schedule_cli.py                       # read the plan (dry run, the default)
  python tools/farm_schedule_cli.py intake --mode live    # queue packages from local preparation
  python tools/farm_schedule_cli.py review                # what waits for approve/reject
  python tools/farm_schedule_cli.py approve 12 --account acct-1
  python tools/farm_schedule_cli.py reject 13 --reason "caption off"
  python tools/farm_schedule_cli.py account acct-1 --daily 2 --gap 180 --cap tiktok=1
  python tools/farm_schedule_cli.py account acct-2 --first-day 2026-11-03 --ramp 0,0,0,1,1,2
  python tools/farm_schedule_cli.py settings --window 9-21 --rack-gap 10 --utc-offset -5 --map tiktok=acct-1
  python tools/farm_schedule_cli.py plan --commit         # record the NEW slots shown by the dry run
  python tools/farm_schedule_cli.py stage-window reel-slot18 --account acct-a18   # queue a prepared window
  python tools/farm_schedule_cli.py run --phone 18 --slots 2 --wait 40   # run due slots on phone 18
  python tools/farm_schedule_cli.py abandon reel18-abc123 --reason "backend log reviewed; nothing saved"

The queue lives at <main folder>/output/farm-schedule/queue.json (not committed); staged windows
and run logs sit beside it (windows/, runs/).
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_paths import MAIN  # noqa: E402
from farm_preparation_schedule import read_prepared_packages  # noqa: E402
from farm_schedule_queue import ReviewQueue  # noqa: E402
import farm_schedule_runner as runner  # noqa: E402

DEFAULT_QUEUE = MAIN / 'output/farm-schedule/queue.json'


def package_id(text): return int(text) if text.isdigit() else text


def pairs(text, value=str):
    out = {}
    for part in filter(None, (text or '').split(',')):
        key, _, raw = part.partition('=')
        if not raw: raise argparse.ArgumentTypeError(f'Expected name=value, got {part!r}.')
        out[key.strip()] = value(raw.strip())
    return out


def main(argv=None, out=sys.stdout):
    parser = argparse.ArgumentParser(description='Review queue and dry-run run plan (no phones, no posting).')
    parser.add_argument('--queue', type=Path, default=DEFAULT_QUEUE)
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    sub = parser.add_subparsers(dest='command')
    plan = sub.add_parser('plan', help='show the plan (dry run); --commit records new slots')
    plan.add_argument('--days', type=int, default=7); plan.add_argument('--commit', action='store_true')
    intake = sub.add_parser('intake', help='queue packages from succeeded local preparation runs')
    intake.add_argument('--preparation-db', type=Path)
    intake.add_argument('--mode', choices=('simulate', 'live'), default='live')
    sub.add_parser('review', help='list packages waiting for approve/reject')
    approve = sub.add_parser('approve'); approve.add_argument('ids', nargs='+', type=package_id); approve.add_argument('--account')
    reject = sub.add_parser('reject'); reject.add_argument('ids', nargs='+', type=package_id); reject.add_argument('--reason', default='')
    unplan = sub.add_parser('unplan', help='take packages off their slots, keep them approved')
    unplan.add_argument('ids', nargs='+', type=package_id)
    stage = sub.add_parser('stage-window', help='queue a freshly prepared window (prepare_window.py) as one package')
    stage.add_argument('window'); stage.add_argument('--account', required=True); stage.add_argument('--id')
    run = sub.add_parser('run', help="run this phone's due slots (phone input, draft only)")
    run.add_argument('--phone', type=int, required=True, help='box slot of the phone, e.g. 18')
    run.add_argument('--slots', type=int, default=1, help='at most this many slot runs')
    run.add_argument('--wait', type=int, default=0, help='minutes to wait for the next slot to come due')
    run.add_argument('--recheck', action='store_true', help='rerun only the read-only verifier once when creation saved but its check stopped')
    abandon = sub.add_parser('abandon', help='a run whose end was never recorded -> stopped, after your review')
    abandon.add_argument('id', type=package_id); abandon.add_argument('--reason', required=True)
    account = sub.add_parser('account', help='per-account daily cap, spacing, platform caps, warmup ramp')
    account.add_argument('account'); account.add_argument('--daily', type=int); account.add_argument('--gap', type=int, help='minutes')
    account.add_argument('--cap', type=lambda t: pairs(t, int), help='platform=N,...')
    account.add_argument('--first-day'); account.add_argument('--ramp', type=lambda t: [int(x) for x in t.split(',') if x])
    settings = sub.add_parser('settings')
    settings.add_argument('--window', type=lambda t: [int(x) for x in t.split('-')], help='e.g. 9-21')
    settings.add_argument('--rack-gap', type=int); settings.add_argument('--utc-offset', type=float)
    settings.add_argument('--default-daily', type=int); settings.add_argument('--default-gap', type=int)
    settings.add_argument('--map', type=pairs, help='platform=account,... default account at intake')
    args = parser.parse_args(argv)
    queue = ReviewQueue(args.queue)
    show = lambda value: out.write(json.dumps(value, indent=1, sort_keys=True) + '\n')
    try:
        if args.command in (None, 'plan'):
            days = getattr(args, 'days', 7)
            if getattr(args, 'commit', False):
                result = queue.plan(days, commit=True)
                if args.json: return show(result) or 0
                out.write(f'Recorded {len(result["proposed"])} new slot(s). Nothing runs on a phone; nothing posts.\n\n')
            if args.json: return show({'plan': queue.plan(days), 'schedule': queue.schedule()}) or 0
            out.write(queue.render(days))
        elif args.command == 'intake':
            db = args.preparation_db or MAIN / f'output/farm-data/v2/{args.mode}/preparation-schedule.db'
            report = queue.intake(read_prepared_packages(db))
            if args.json: return show(report) or 0
            out.write(f'{db}: {len(report["added"])} added, {len(report["known"])} already queued, {len(report["refused"])} refused.\n')
            for refused in report['refused']: out.write(f'  refused {refused["id"]}: {refused["reason"]}\n')
        elif args.command == 'review':
            waiting = queue.pending()
            if args.json: return show(waiting) or 0
            if not waiting: out.write('Nothing waits for review.\n')
            for p in waiting:
                out.write(f'pkg {p["id"]}  {p["platform"]}/{p["format"]}  account {p["account"] or "(set with --account)"}\n'
                          f'  caption: {p["caption"]}\n')
                for name in p['source'].get('stagedFiles', []): out.write(f'  file: {name}\n')
        elif args.command in ('approve', 'reject', 'unplan'):
            for pid in args.ids:
                if args.command == 'approve': pkg = queue.approve(pid, args.account)
                elif args.command == 'reject': pkg = queue.reject(pid, args.reason)
                else: pkg = queue.unplan(pid)
                out.write(f'pkg {pkg["id"]}: {pkg["state"]}\n')
        elif args.command == 'stage-window':
            pkg = runner.stage_window(runner.WindowSteps(args.queue.parent / 'windows'), queue, args.window, args.account, args.id)
            out.write(f'pkg {pkg["id"]}: {pkg["state"]} ({pkg["platform"]}/{pkg["format"]}, phone {pkg["source"]["slot"]}, '
                      f'test package "{pkg["caption"]}")\n')
        elif args.command == 'run':
            steps = runner.WindowSteps(args.queue.parent / 'windows')
            log = lambda line: (out.write(line + '\n'), out.flush())
            with runner.phone_lock(args.queue.parent / f'phone-{args.phone}.lock'):
                records = runner.SlotRunner(queue, steps, args.phone, recheck=args.recheck, log=log).run(args.slots, args.wait * 60)
            if args.json: return show(records) or 0
            if not records: out.write(f'No slot was due on phone {args.phone}.\n')
        elif args.command == 'abandon':
            pkg = queue.abandon(args.id, args.reason); out.write(f'pkg {pkg["id"]}: {pkg["state"]}\n')
        elif args.command == 'account':
            result = queue.set_account(args.account, args.daily, args.gap, args.cap, args.first_day, args.ramp)
            show({args.account: result})
        elif args.command == 'settings':
            show(queue.set_settings(args.window, args.rack_gap, args.utc_offset, args.map, args.default_daily, args.default_gap))
    except ValueError as exc:
        print(f'Refused: {exc}', file=sys.stderr); return 2
    return 0


if __name__ == '__main__': sys.exit(main())
