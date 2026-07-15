#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <seccomp.h>
#include <sys/prctl.h>

static int install(void){
    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ALLOW);

    if(!ctx) return -1;

    int rc = 0;
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(socket), 0);
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(socketpair), 0);

    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(memfd_create), 0);
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(shmget), 0);
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(shmat), 0);

    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(mknod), 0);
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(mknodat), 0);

    const unsigned WR = O_WRONLY|O_RDWR|O_CREAT|O_APPEND;
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(openat), 1,
                           SCMP_A2(SCMP_CMP_MASKED_EQ, O_WRONLY, O_WRONLY));
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(openat), 1,
                           SCMP_A2(SCMP_CMP_MASKED_EQ, O_RDWR,   O_RDWR));
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(openat), 1,
                           SCMP_A2(SCMP_CMP_MASKED_EQ, O_CREAT,  O_CREAT));
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(open), 1,
                           SCMP_A1(SCMP_CMP_MASKED_EQ, O_WRONLY, O_WRONLY));
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(open), 1,
                           SCMP_A1(SCMP_CMP_MASKED_EQ, O_RDWR,   O_RDWR));
    rc |= seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(open), 1,
                           SCMP_A1(SCMP_CMP_MASKED_EQ, O_CREAT,  O_CREAT));
    (void)WR;

    if(rc){ seccomp_release(ctx); return -1; }

    if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)){ seccomp_release(ctx); return -1; }

    rc = seccomp_load(ctx);
    seccomp_release(ctx);

    return rc;
}

int main(int argc, char** argv){
    int i=1;
    if(i<argc && strcmp(argv[i],"--gate-pipe")==0){
        int p[2]; if(pipe(p)==0){ char b[16]; snprintf(b,sizeof b,"%d",p[1]); setenv("SG_GATE_FD",b,1);} i++;
    }
    if(i>=argc){ fprintf(stderr,"usage: confine [--gate-pipe] <cmd> [args]\n"); return 2; }
    if(install()){ perror("seccomp"); return 3; }
    execvp(argv[i], &argv[i]);
    perror("execvp"); return 4;
}