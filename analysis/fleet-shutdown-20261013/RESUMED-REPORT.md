# Receiver fleet shutdown repair

13 October 2026. Resumed at the operator's request from `e82117e`. Offline only: no desktop control, rack call, real receiver, HID, phone input or installed-release operation.

## Reproduction and repair

The preserved draft was recovered after checking the active recovery sources against their original revision. Its fixture lifetime was corrected first: fixture teardown now has its own asynchronous path and does not call the fake receiver's simulated disposal a second time.

Against the unchanged product source, all five added checks failed. Shutdown returned while cleanup was already running, delayed stopping a peer behind one slow receiver, silently accepted unconfirmed cleanup, returned early to a concurrent shutdown caller, and accepted startup after disposal. The existing 29 checks passed in the unrestricted offline run. `resumed/before-source`, `before-manifest.json`, the binary and logs preserve this comparison. The earlier restricted run also encountered three temporary log-rotation permission failures; those are environment failures, not additional product defects.

`ReceiverFleet` now retains frame-reader and supervisor tasks, allows startup only once, and shares one shutdown task among all callers. Each session's stop is requested independently; shutdown then joins both the disposal path and the supervisor run that may already own cleanup, plus the frame reader. Failures identify their receiver and are collected after all peers have been handled. A private frame pipe is demonstrably closed before successful shutdown returns.

`AirplaySupervisor` exposes its distinct cleanup-failure outcome to the fleet. Ordinary retry exhaustion with no remaining child is not mislabeled as unconfirmed cleanup. The kernel closes the API/input sessions before awaiting fleet shutdown and reports an incomplete shutdown with a nonzero exit result. Its exception path also awaits cleanup. Receiver arguments, retry limits, HID commands and the installed release are unchanged.

## Verification

| Check | Result |
|---|---|
| Original source with five corrected draft checks | **29/34**; all five targeted cases fail |
| First repaired build | **34/34** |
| Expanded recovery suite | **41/41**, including seven added startup/cancellation/pipe/failure cases |
| Final kernel self-tests | **207 passed**; simulated HID only |
| Frame tests | **34/34** |
| Receiver lifetime tests | **14/14**; fake processes only |
| Release builds | Zero warnings/errors |
| Installed static files, configuration and operator settings | Match the previously recorded restoration hashes; active receiver logs excluded |

Expanded cases cover disposal during a synchronous factory, already-cancelled startup, repeated startup, partial-start cleanup failure carrying a last known PID, exhausted retries without a child, releasing an actual private test pipe, and multiple failed children reported to repeated shutdown callers. Fake startup/cleanup gates have failsafes; fixture teardown releases them and awaits completion. The real-child lifetime tests from the prior repair were not rerun because that implementation was unchanged. No end-to-end native kernel shutdown or exit-code injection was exercised; the entry-point wiring was compiled and reviewed.

## Exact build and limits

Kernel DLL SHA-256: `cd0f2129993f93158f7fcf183e590a9c1fe1be4c329de0903a2aef3de1dd7486`.
The version stamp has base `e82117e`; `resumed/kernel-manifest.json` records the exact source including working changes and all five output files. Recovery, frame and lifetime manifests include linked production inputs. The earlier untouched draft and pause archive remain preserved.

The existing receiver-root exit wait remains five seconds. This does not establish a fleet-wide upper bound on a stuck native startup call, thread-pool scheduling or arbitrary cleanup callback. It does not attest descendant-process exit, live UxPlay teardown, phone recasting or the historical discovery delay. No acceptance gate advances. Assemble this kernel with the already verified screenshot-client console repair before another approved physical window; never modify the older immutable package to imply it contains these changes.
