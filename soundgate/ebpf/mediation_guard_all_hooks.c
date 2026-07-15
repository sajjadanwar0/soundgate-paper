#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define GATE_IP   0x0100007f
#define GATE_PORT 8796

SEC("cgroup/connect4")
int restrict_connect4(struct bpf_sock_addr *ctx) {
    if (ctx->user_ip4 == GATE_IP && bpf_ntohs(ctx->user_port) == GATE_PORT)
        return 1;

    return 0;
}

SEC("cgroup/connect6")

int restrict_connect6(struct bpf_sock_addr *ctx) {
    return 0;
}

SEC("cgroup/sendmsg4")

int restrict_sendmsg4(struct bpf_sock_addr *ctx) {
    return 0;
}

SEC("cgroup/sendmsg6")

int restrict_sendmsg6(struct bpf_sock_addr *ctx) {
    return 0;
}

char _license[] SEC("license") = "GPL";