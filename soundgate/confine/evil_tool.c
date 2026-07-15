#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <linux/memfd.h>

static const char* verdict(int ok){ return ok ? "ESCAPED (leak)" : "refused"; }

int main(void){
    int leaks = 0;

    int fd = open("/tmp/sg_exfil.txt", O_WRONLY|O_CREAT|O_TRUNC, 0644);
    int fs_ok = (fd >= 0);

    if (fs_ok){ (void)!write(fd, "exfil\n", 6); close(fd); leaks++; }
    printf("  filesystem  write /tmp/sg_exfil.txt : %s (%s)\n", verdict(fs_ok), fs_ok?"":strerror(errno));

    int s = socket(AF_UNIX, SOCK_STREAM, 0);
    int ipc_ok = (s >= 0);

    if (ipc_ok){ close(s); leaks++; }
    printf("  ipc         socket(AF_UNIX)         : %s (%s)\n", verdict(ipc_ok), ipc_ok?"":strerror(errno));

    long m = syscall(SYS_memfd_create, "sg_shm", 0);
    int shm_ok = (m >= 0);

    if (shm_ok){ close((int)m); leaks++; }
    printf("  shared-mem  memfd_create            : %s (%s)\n", verdict(shm_ok), shm_ok?"":strerror(errno));

    const char* gfd = getenv("SG_GATE_FD");

    if (gfd){
        int g = atoi(gfd);
        int gate_ok = (write(g, "{\"op\":\"submit\"}\n", 16) >= 0);
        printf("  gate        write(inherited fd %d)   : %s (%s)\n", g,
               gate_ok?"admitted (mediated path works)":"refused", gate_ok?"":strerror(errno));
    }

    printf("RESULT: %d of 3 non-network channels ESCAPED\n", leaks);
    return leaks; /* exit code = number of leaks */
}