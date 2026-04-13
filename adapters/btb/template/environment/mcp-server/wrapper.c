#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>

int main(void) {
    /* Capture the real caller UID before privilege elevation */
    uid_t caller_uid = getuid();
    char caller_uid_str[32];
    snprintf(caller_uid_str, sizeof(caller_uid_str), "%u", (unsigned)caller_uid);

    /* Set real GID/UID to match effective (setuid file owner = environment) */
    if (setgid(getegid()) != 0) {
        perror("setgid");
        return 1;
    }
    if (setuid(geteuid()) != 0) {
        perror("setuid");
        return 1;
    }

    /* Pass the original caller UID to the server */
    setenv("MCP_CALLER_UID", caller_uid_str, 1);
    setenv("HOME", "/home/environment", 1);
    chdir("/opt/mcp-server");

    char *args[] = {"uv", "run", "python", "server.py", NULL};
    execv("/usr/local/bin/uv", args);

    perror("execv");
    return 1;
}
