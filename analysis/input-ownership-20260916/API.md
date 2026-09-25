# Input ownership API, protocol 1

This API is implemented only in the staged ownership kernel. It is not a reason
to change the desktop shortcut before compatible console validation.

GET `/api/kernel/status` advertises `data.input_protocol: 1` and
`data.input_leases_required: true`. GET `/api/input/status` returns per-phone
`owned`, `active`, `stopped`, `releasing`, `release_failed`, `message`, and
`lease_remaining_ms`. Status never exposes lease tokens.

POST requests keep the existing envelope:

```json
{"fun":"/input/acquire","data":{"id":"PHONE_ID","lease_ms":30000}}
```

The normal response envelope remains `status: 200`, with operation results in
`data`. Inspect `data.code`; HTTP 200 alone does not mean a command succeeded.

| Function | Required data | Result/behavior |
|---|---|---|
| `/input/acquire` | `id` (one or comma-separated IDs); optional `lease_ms` | `code:0, leases:[{id,token,lease_ms}]`. All acquisitions succeed together or return conflict. |
| `/input/renew` | `id` and matching token(s) | Renews by the original lease duration; an expired lease cannot be revived. |
| `/input/release` | `id` and matching token(s) | Cancels active work, releases held inputs, revokes tokens. Does not normally latch Stop. |
| `/input/stop` | `id` | Revokes ownership and cancels/releases input. Any local operator may stop. |
| `/input/resume` | `id` | Clears a successful Stop only after cleanup. Does not restore any old token or replay commands. |
| existing `/mouse/*`, `/key/sendkey` | existing arguments plus matching token(s) | Same HID behavior, through ownership validation; at most one active command per board. |

Single-phone command:

```json
{"fun":"/mouse/click","data":{"id":"PHONE_ID","token":"ACQUIRED_TOKEN","x":250,"y":900}}
```

Explicit group command:

```json
{"fun":"/key/sendkey","data":{"id":"PHONE_A,PHONE_B","tokens":{"PHONE_A":"TOKEN_A","PHONE_B":"TOKEN_B"},"fn_key":"Home"}}
```

Groups preflight every target/token/argument. Once execution starts, one board
can fail while another succeeds; inspect per-phone `results`. Never automatically
retry the entire group because one member failed.

Code 409 means missing/invalid ownership, stopped/recovering state, or a conflicting
active command. Code 36 means bad arguments. Code 33 means execution/cleanup
failure; individual canceled commands have code 499 in `results`. Code 41 marks
unsupported functions, including live rebinding in this build.

Client contract:

1. Discover capability; never send real input to an incompatible kernel silently.
2. Acquire before input, keep the token private to that controller, and serialize
   commands within its phone session. Different phone sessions may run concurrently.
3. Keep one lease across the complete drag or workflow. Renew independently of
   the ordinary command queue, typically every ten seconds with the default lease.
4. Stop bypasses the client input queue. Cancel local drag/hover work as well.
   Await server cleanup/status before enabling explicit Resume.
5. Drop cached tokens after Stop, expiry, release, reconnection, or any ownership
   conflict. Do not automatically resume or reacquire to replay a rejected click.
6. On selection/group changes, finish/cancel the old gesture before releasing its
   lease. Update group membership deliberately; never leave hidden owned phones.
7. Do not retry non-idempotent input after an ambiguous timeout. Show the outcome
   as uncertain and inspect the phone.

Existing legacy input callers without tokens are rejected by this staged kernel.
The current desktop app stays on its existing release until integration passes.
