"""Reuse the strict two-phone checker while preserving the previous test artifacts."""
import two_phone_check as check
check.OUT = check.ROOT / 'analysis' / 'candidate-validation-20260915'
check.OUT.mkdir(parents=True, exist_ok=True)
if __name__ == '__main__':
    check.main()
