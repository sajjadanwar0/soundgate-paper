// mediation_guard_all_hooks.c -- COMPLETE-channel egress mediation (reviewer W2:
// "connect4 only; what about IPv6, sendmsg, io_uring, filesystem, IPC?").
//
// Policy: a process in the attached cgroup may reach the SoundGate address and
// NOTHING else, on EVERY network egress channel the kernel exposes a cgroup
// hook for. The gate is TCP v4 loopback (127.0.0.1:8796), so:
//   * connect4  -> ALLOW only the gate; deny all other IPv4 connects
//   * connect6  -> DENY all (no v6 gate); closes the IPv6 connect channel
//   * sendmsg4  -> DENY all (gate is TCP, not UDP); closes unconnected v4 datagrams
//   * sendmsg6  -> DENY all; closes unconnected v6 datagrams
//   * recvmsg4/6 are ingress, not egress, and are left to the netns/firewall
//
// io_uring: IORING_OP_CONNECT/SEND route through the same socket egress path,
// so on kernels where the cgroup sock_addr hooks fire for io_uring-submitted
// ops (>=5.13 for connect; verify on your target) they are covered here. If you
// must defeat a kernel that bypasses the hooks, pair this with a seccomp filter
// denying io_uring_setup(2) for the tool process (the seccomp complement is the
// belt to this cgroup braces).
//
// NON-NETWORK effect channels (shared filesystem, local IPC, shared memory) are
// deliberately OUT of this program's scope and are mediated by the paper's
// stated placement contract or an LSM/seccomp policy -- every effect the gate
// exists to govern (email, payment capture, ticket, deploy) externalizes over
// the network, which is exactly what this closes. State that boundary; do not
// claim this file mediates file writes.
//
// LOAD (all four, one cgroup):
//   clang -O2 -g -target bpf -c mediation_guard_all_hooks.c -o mediation_guard_all_hooks.o
//   for s in connect4 connect6 sendmsg4 sendmsg6; do \
//     bpftool prog load mediation_guard_all_hooks.o /sys/fs/bpf/mg_$s \
//       type cgroup/$s pinmaps /sys/fs/bpf/mg_maps 2>/dev/null; \
//     bpftool cgroup attach /sys/fs/cgroup/soundgate $s pinned /sys/fs/bpf/mg_$s; \
//   done
//   bpftool cgroup show /sys/fs/cgroup/soundgate   # expect 4 programs attached
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define GATE_IP   0x0100007f   // 127.0.0.1, network byte order on LE host
#define GATE_PORT 8796

// IPv4 connect: allow only the gate.
SEC("cgroup/connect4")
int restrict_connect4(struct bpf_sock_addr *ctx) {
    if (ctx->user_ip4 == GATE_IP && bpf_ntohs(ctx->user_port) == GATE_PORT)
        return 1;              // ALLOW
    return 0;                  // DENY (EPERM at connect())
}

// IPv6 connect: no v6 gate -> deny everything.
SEC("cgroup/connect6")
int restrict_connect6(struct bpf_sock_addr *ctx) {
    return 0;                  // DENY all v6 egress
}

// Unconnected IPv4 datagrams (sendto/sendmsg): gate is TCP -> deny.
SEC("cgroup/sendmsg4")
int restrict_sendmsg4(struct bpf_sock_addr *ctx) {
    return 0;                  // DENY all unconnected v4 sends
}

// Unconnected IPv6 datagrams: deny.
SEC("cgroup/sendmsg6")
int restrict_sendmsg6(struct bpf_sock_addr *ctx) {
    return 0;                  // DENY all unconnected v6 sends
}

char _license[] SEC("license") = "GPL";