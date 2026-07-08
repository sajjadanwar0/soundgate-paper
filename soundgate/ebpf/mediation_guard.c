// mediation_guard.c -- cgroup/connect4 eBPF program: a process in the
// attached cgroup may open outbound IPv4 connections ONLY to the SoundGate
// address (127.0.0.1:8796 by default). Every other destination is refused
// by the kernel at connect() time -- this is what "structurally forces all
// outgoing effects through the gate" means: not a wrapper convention, a
// kernel policy the tool process cannot opt out of.
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define GATE_IP   0x0100007f   // 127.0.0.1 in network byte order (little-endian host)
#define GATE_PORT 8796

SEC("cgroup/connect4")
int restrict_egress(struct bpf_sock_addr *ctx) {
    if (ctx->user_ip4 == GATE_IP &&
        bpf_ntohs(ctx->user_port) == GATE_PORT) {
        return 1;  // ALLOW: this is the gate
    }
    return 0;      // DENY: everything else, kernel-enforced
}

char _license[] SEC("license") = "GPL";
