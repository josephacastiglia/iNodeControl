# Isolated Windows test environment: plan, 27 Sep 2026

**Status: plan only.** Nothing was installed, enabled, rebooted or reconfigured. No host desktop automation was run while planning. Every host fact below was read-only. The working release, kernel, receivers and installed console are unchanged.

## Goal

A Windows virtual machine where Claude and its desktop-control tools run entirely inside the guest:
- **Phones:** simulated only, from the mock kernel. No rack connection and no USB access.
- **Host:** the host's mouse, focus and rack are never involved.

It is the only place further console click reproduction should happen. The click investigation is closed on the working desktop (`analysis/console-click-investigation-20260927/`).

## Host assessment (read-only)

| Item | Finding |
|---|---|
| OS | Windows 11 **Home** 10.0.26200, 64-bit |
| CPU | AMD Ryzen 7 7700X, 8 cores / 16 threads; virtualization enabled in firmware |
| Hypervisor | **Already running** (`HypervisorPresent` true, `hypervisorlaunchtype Auto`). WMI reports SLAT false, as it does when read from inside the running hypervisor |
| Windows features | Virtual Machine Platform **on** (WSL2, Docker). Windows Subsystem for Linux on. **Windows Hypervisor Platform off.** Hyper-V and Windows Sandbox are not available on Home |
| Security | VBS running; memory integrity (HVCI) not running |
| RAM | 63.1 GB total, about 40 GB free at the time |
| Disk | C: NVMe SSD (Solidigm, 1.9 TB), 508 GB free. D: and H: are USB hard drives; do not use them for a VM |
| Installed | **VMware Workstation 17.6.2**: services running, VMnet1 (host-only) and VMnet8 (NAT) present, 2 existing VMs in its inventory (leave untouched). **VirtualBox 7.0.18**: two inaccessible VM registrations. WSL2: Ubuntu and docker-desktop, both stopped |
| Rack load at the time | Kernel, 2 receivers and the installed console: under 500 MB RAM together; host CPU about 5% |

## The one blocker

With the Windows hypervisor already running, VMware Workstation and VirtualBox can run VMs only through **Windows Hypervisor Platform**, which is off.

Options:
1. **Enable Windows Hypervisor Platform (recommended).** One Windows feature and one reboot. WSL2, Docker and VBS keep working. It needs your approval and a planned rack downtime: the kernel, receivers and AirPlay sessions stop across the reboot.
2. **Turn the hypervisor off** (`hypervisorlaunchtype off`). This breaks WSL2 and Docker and turns off VBS. Not recommended.

**Recommended hypervisor: VMware Workstation 17.6.2** (already installed; free for personal use), running on Windows Hypervisor Platform. VirtualBox 7.0 on the same platform is the fallback; it is usually slower and less stable there.

## Guest

- **OS:** Windows 11 x64. The host's Home licence does not cover a VM. Either use the 90-day Windows 11 Enterprise evaluation or a purchased licence. That is your decision.
- **Hardware:**
  - 4 vCPUs (the host keeps 12 threads for the rack);
  - 8 GB RAM, or 12 GB if builds run in the guest;
  - a 96 GB growable disk on C:;
  - UEFI with Secure Boot and a virtual TPM (VMware needs VM encryption for the vTPM).
- **Display:** 1920×1080 at 100% scaling. Today's per-monitor DPI and maximize quirk came from moving a window between monitors with different scaling.
- **Snapshots:** `clean-os` after setup, `tools-installed` after the drop, and a revert after every session.

## Isolation controls

| Control | Setting | Why |
|---|---|---|
| USB | **Remove the USB controller**; turn off auto-connect of new USB devices | No path for a control board or phone into the guest |
| Serial, parallel, printer, sound input | Remove | Nothing to reach |
| Shared folders | None, or one **read-only** share of a dedicated `iMouseXP-2.0-vm-drop` folder | Never the release folder, repository, evidence archive or `analysis/two-phone-config` |
| Clipboard and drag-and-drop | Off in VMware Tools | No data path between host and guest |
| Network | **NAT (existing VMnet8) only**, no bridged adapter; no host networking changes | Claude needs the internet |
| Guest firewall | Block outbound to private ranges (10/8, 172.16/12, 192.168/16, 169.254/16) except the NAT gateway's DNS | The guest can't reach the host's LAN addresses, the AirPlay receivers or the phones. The kernel listens only on host loopback (127.0.0.1:9913), which a guest cannot reach anyway |
| Input capture | VMware: don't grab input on click; release on mouse-out | Your host mouse is never captured by the VM window |
| Contents | Only the candidate build, the mock (`input-cleanup-harness`), the fault proxy and `tools/click-probe` | No kernel, receiver, calibration or rack configuration in the guest |

## Claude inside the guest

- **Install:** Claude desktop in the guest. **You sign in yourself**; Claude must not enter credentials.
- **Repository:** a separate clone, brought in as a git bundle through the drop folder. Guest sessions never see host paths.
- **Tools:** computer use and the built-in browser act only on the guest desktop.

## Mock kernel (already implemented, harness only)

`InputCleanupHarness.exe --serve PORT [BOARDPID]` now:
- **Refuses a taken port.** Startup fails with **exit 3** if anything already holds PORT on loopback, including an http.sys registration for a sub-path, which is how the 27 Sep bypass happened.
- **Hides its inner server.** The inner ApiServer runs on a dynamic port under a random secret path, so nothing but the mock's own front can reach the kernel code that enumerates real boards.
- **Answers the board list itself.** The front returns only the simulated board F001 and forwards everything else to the inner server.
- **Checks itself at startup.** It reads its board and device lists through PORT, and exits with **exit 4** unless they are exactly F001 and SIM:01.
- **Regression checks:**
  - S7: an http.sys `/api/` squatter gives exit 3, and so does a plain socket.
  - S8: on a free port the mock starts, self-checks, serves only F001 and frees the port on stop.
  - Both pass with S1–S6 on the host build.
- **In the guest** there is also no board hardware at all, because the USB controller is removed.

## Verification before any testing (in order, each must pass)

1. **Host baseline (read-only, on host):**
   - kernel, receiver and console PIDs and paths;
   - lease state for both phones;
   - operator settings hash `72F51CC0…`.
2. **Guest hardware:**
   - `Get-PnpDevice -Class USB` shows no USB host controller;
   - there are no shared folders, or only the read-only drop;
   - there is a single NAT adapter.
3. **Guest network isolation.** From the guest:
   - the host's LAN address on 9913 and the AirPlay ports (7000, 7100) is unreachable;
   - `127.0.0.1:9913` answers nothing;
   - Claude's service is reachable.
4. **Mock safety in the guest:**
   - run the harness (S1–S8 must pass);
   - start `--serve` twice on the same port: the second must exit 3.
5. **Click delivery in the guest.** Run the instrumented console (`IMOUSE_INPUT_TRACE`) against the mock, with `Watch-MouseButtons.ps1` running in the guest.
   - Every computer-use click must appear at the system hook, as `WM_LBUTTONDOWN`, and as `Click`.
   - Also record whether `SendInput` from the guest agent's shell works. On the host it silently did nothing.
6. **Host non-interference.** While the guest agent clicks for about 2 minutes, a read-only host monitor, started with your approval, samples three things. All three must stay unchanged or zero:
   - the host cursor position (`GetCursorPos`, every 100 ms);
   - the host foreground window;
   - host button events (`Watch-MouseButtons -WatchSeconds`).

   Repeat with the VMware window unfocused and then minimized, to confirm the guest agent needs no host focus.
7. Only then resume click-reproduction work, in the guest.

## Needs your approval (none done)

1. Enable Windows Hypervisor Platform, and schedule the reboot together with rack downtime.
2. Choose the guest licence and download the Windows 11 ISO (about 6 GB).
3. Create the VM in VMware Workstation, using the existing VMnet8 with no host networking changes.
4. Install Claude desktop in the guest and sign in.
5. Create the drop folder and transfer the build.

## Risks

- **CPU contention with the rack.** Chunk timing proved CPU-sensitive (the 8,021 ms overrun). Cap the VM at 4 vCPUs, run guest sessions when the rack is idle, and watch host load.
- **Performance.** Windows Hypervisor Platform is slower than bare virtualization; this is adequate for a WPF console and a mock.
- **Existing VMs and adapters.** The existing VMware VMs and adapters stay untouched. The new VM uses its own folder on C:.
- **Physical phones stay out.** They remain on the host rack. This plan gives the guest no rack access; any future need would get a separate plan.
