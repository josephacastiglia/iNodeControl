"""Strict two-phone checks; separate evidence directory for pointer investigation."""
import two_phone_check as check
check.OUT = check.ROOT / 'analysis' / 'pointer-reliability-20260915'
check.OUT.mkdir(parents=True, exist_ok=True)
if __name__ == '__main__':
    check.main()
