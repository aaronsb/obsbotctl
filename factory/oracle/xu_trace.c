// xu_trace: an LD_PRELOAD shim that records UVC traffic made through libc.
//
// It wraps open/openat to remember which descriptors are /dev/video* nodes,
// and wraps ioctl to log, on those descriptors:
//   - every UVC extension-unit query (UVCIOC_CTRL_QUERY) with unit,
//     selector, query type, size and payload. SET payloads are logged
//     before the call, GET payloads after it, so each line shows the bytes
//     that actually crossed the wire.
//   - every other ioctl request code, by number, so V4L2 control traffic
//     is visible too.
// Output goes to the file named by XU_TRACE_FILE, or stderr.
//
// Build: cc -shared -fPIC -O2 -o xu_trace.so xu_trace.c -ldl
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/usb/video.h>
#include <linux/uvcvideo.h>
#include <linux/videodev2.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <ctype.h>
#include <strings.h>
#include <unistd.h>

#define MAX_FD 4096
static char is_video[MAX_FD];
static FILE *out;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;

static void init_out(void) {
    if (out) return;
    const char *p = getenv("XU_TRACE_FILE");
    out = p ? fopen(p, "a") : NULL;
    if (!out) out = stderr;
    setvbuf(out, NULL, _IOLBF, 0);
}

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static const char *qname(unsigned q) {
    switch (q) {
    case UVC_SET_CUR: return "SET_CUR";
    case UVC_GET_CUR: return "GET_CUR";
    case UVC_GET_MIN: return "GET_MIN";
    case UVC_GET_MAX: return "GET_MAX";
    case UVC_GET_RES: return "GET_RES";
    case UVC_GET_LEN: return "GET_LEN";
    case UVC_GET_INFO: return "GET_INFO";
    case UVC_GET_DEF: return "GET_DEF";
    default: return "?";
    }
}

static void hex(const unsigned char *d, unsigned n) {
    for (unsigned i = 0; i < n; i++) fprintf(out, "%02x", d[i]);
}

static void note_open(int fd, const char *path) {
    if (path && getenv("XU_TRACE_SYSFS") && strncmp(path, "/sys/", 5) == 0) {
        pthread_mutex_lock(&lock);
        init_out();
        fprintf(out, "%.6f sysfs-open fd=%d %s\n", now(), fd, path);
        pthread_mutex_unlock(&lock);
    }
    if (fd >= 0 && fd < MAX_FD) {
        is_video[fd] = path && strncmp(path, "/dev/video", 10) == 0;
        if (is_video[fd]) {
            pthread_mutex_lock(&lock);
            init_out();
            fprintf(out, "%.6f open fd=%d %s\n", now(), fd, path);
            pthread_mutex_unlock(&lock);
        }
    }
}


static void note_sys(const char *what, const char *path) {
    if (path && getenv("XU_TRACE_SYSFS") && strncmp(path, "/sys/", 5) == 0) {
        pthread_mutex_lock(&lock);
        init_out();
        fprintf(out, "%.6f sysfs-%s %s\n", now(), what, path);
        pthread_mutex_unlock(&lock);
    }
}

// USB-ID substitution, for oracle runs. When XU_FAKE_PID is set (hex, such
// as "fef8"), a read of a sysfs idProduct file that holds XU_REAL_PID
// (default "fefb") returns the fake ID instead, and a modalias file has its
// "p<PID>" field rewritten to match. Only what the library reads is changed.
static FILE *substitute(FILE *(*real)(const char *, const char *), const char *path, const char *mode) {
    const char *fake = getenv("XU_FAKE_PID");
    if (!fake || !path || strncmp(path, "/sys/", 5) != 0 || strchr(mode, 'w')) return NULL;
    const char *real_pid = getenv("XU_REAL_PID") ? getenv("XU_REAL_PID") : "fefb";
    size_t n = strlen(path);
    int is_pid = n > 10 && strcmp(path + n - 10, "/idProduct") == 0;
    int is_alias = n > 9 && strcmp(path + n - 9, "/modalias") == 0;
    if (!is_pid && !is_alias) return NULL;
    FILE *f = real(path, mode);
    if (!f) return NULL;
    static char text[8][512]; static int slot;
    char *buf = text[slot++ % 8];
    size_t got = fread(buf, 1, 511, f); buf[got] = 0; fclose(f);
    if (is_pid) {
        if (strncasecmp(buf, real_pid, strlen(real_pid)) == 0) {
            snprintf(buf, 512, "%s\n", fake);
            fprintf(out ? out : stderr, "%.6f substitute %s -> %s\n", now(), path, fake);
        }
    } else {
        char want[16], repl[16];
        snprintf(want, sizeof want, "p%s", real_pid); snprintf(repl, sizeof repl, "p%s", fake);
        for (char *c = want + 1; *c; c++) *c = (char)toupper((unsigned char)*c);
        for (char *c = repl + 1; *c; c++) *c = (char)toupper((unsigned char)*c);
        char *at = strstr(buf, want);
        if (at && strlen(want) == strlen(repl)) {
            memcpy(at, repl, strlen(repl));
            fprintf(out ? out : stderr, "%.6f substitute %s pid -> %s\n", now(), path, fake);
        }
    }
    // Hand back a real file, not an in-memory stream: the library may read
    // through the file descriptor, which an fmemopen() stream does not have.
    char tmpl[] = "/tmp/xu_trace_sysfs_XXXXXX";
    int tfd = mkstemp(tmpl);
    if (tfd < 0) return NULL;
    ssize_t w = write(tfd, buf, strlen(buf));
    close(tfd);
    FILE *r = (w < 0) ? NULL : real(tmpl, "r");
    unlink(tmpl);
    return r;
}

FILE *fopen(const char *path, const char *mode) {
    static FILE *(*real)(const char *, const char *);
    if (!real) real = dlsym(RTLD_NEXT, "fopen");
    note_sys("fopen", path);
    FILE *s = substitute(real, path, mode);
    return s ? s : real(path, mode);
}

FILE *fopen64(const char *path, const char *mode) {
    static FILE *(*real)(const char *, const char *);
    if (!real) real = dlsym(RTLD_NEXT, "fopen64");
    note_sys("fopen64", path);
    FILE *s = substitute(real, path, mode);
    return s ? s : real(path, mode);
}

#include <dirent.h>
DIR *opendir(const char *path) {
    static DIR *(*real)(const char *);
    if (!real) real = dlsym(RTLD_NEXT, "opendir");
    note_sys("opendir", path);
    return real(path);
}

ssize_t readlink(const char *path, char *buf, size_t n) {
    static ssize_t (*real)(const char *, char *, size_t);
    if (!real) real = dlsym(RTLD_NEXT, "readlink");
    note_sys("readlink", path);
    return real(path, buf, n);
}

int open(const char *path, int flags, ...) {
    static int (*real)(const char *, int, ...);
    if (!real) real = dlsym(RTLD_NEXT, "open");
    mode_t mode = 0;
    if (flags & (O_CREAT | O_TMPFILE)) { va_list a; va_start(a, flags); mode = va_arg(a, mode_t); va_end(a); }
    int fd = real(path, flags, mode);
    note_open(fd, path);
    return fd;
}

int open64(const char *path, int flags, ...) {
    static int (*real)(const char *, int, ...);
    if (!real) real = dlsym(RTLD_NEXT, "open64");
    mode_t mode = 0;
    if (flags & (O_CREAT | O_TMPFILE)) { va_list a; va_start(a, flags); mode = va_arg(a, mode_t); va_end(a); }
    int fd = real(path, flags, mode);
    note_open(fd, path);
    return fd;
}

int openat(int dirfd, const char *path, int flags, ...) {
    static int (*real)(int, const char *, int, ...);
    if (!real) real = dlsym(RTLD_NEXT, "openat");
    mode_t mode = 0;
    if (flags & (O_CREAT | O_TMPFILE)) { va_list a; va_start(a, flags); mode = va_arg(a, mode_t); va_end(a); }
    int fd = real(dirfd, path, flags, mode);
    note_open(fd, path);
    return fd;
}

// CRC-16/USB: reflected polynomial 0x8005, start 0xFFFF, result inverted.
static unsigned short crc16_usb(const unsigned char *d, unsigned n) {
    unsigned c = 0xFFFF;
    for (unsigned i = 0; i < n; i++) {
        c ^= d[i];
        for (int b = 0; b < 8; b++) c = (c & 1) ? (c >> 1) ^ 0xA001 : c >> 1;
    }
    return (unsigned short)(c ^ 0xFFFF);
}

// Identity rewrite, for oracle runs. When XU_FAKE_DEVINFO is set, the reply
// to UG_GET_DEV_INFO (opcode 0x1948) has payload bytes replaced, and both
// CRCs are recomputed so the vendor library accepts it. The variable is a
// comma-separated list of offset=value pairs into the payload, for example
// "0=2,2=2". Nothing is sent to the camera; only the reply the library reads
// is changed.
static void maybe_rewrite_identity(unsigned char *d, unsigned size) {
    const char *fake = getenv("XU_FAKE_DEVINFO");
    if (!fake || size < 18 || d[0] != 0xaa || d[4] != 12) return;
    if (d[10] != 0x48 || d[11] != 0x19) return;
    unsigned len = d[12] | d[13] << 8;
    if (len < 1 || 16 + len > size) return;
    char buf[256];
    strncpy(buf, fake, sizeof buf - 1); buf[sizeof buf - 1] = 0;
    for (char *tok = strtok(buf, ","); tok; tok = strtok(NULL, ",")) {
        char *eq = strchr(tok, '=');
        if (!eq) continue;
        unsigned off = (unsigned)strtoul(tok, NULL, 0), v = (unsigned)strtoul(eq + 1, NULL, 0);
        if (off >= len) continue;
        fprintf(out, "%.6f rewrite devinfo[%u] %u -> %u\n", now(), off, d[16 + off], v & 0xff);
        d[16 + off] = v & 0xff;
    }
    d[14] = d[15] = 0;
    unsigned short pc = crc16_usb(d + 12, 4 + len);
    d[14] = pc & 0xff; d[15] = pc >> 8;
    d[6] = d[7] = 0;
    unsigned short hc = crc16_usb(d, 12);
    d[6] = hc & 0xff; d[7] = hc >> 8;
}

int ioctl(int fd, unsigned long req, ...) {
    static int (*real)(int, unsigned long, ...);
    if (!real) real = dlsym(RTLD_NEXT, "ioctl");
    va_list a; va_start(a, req); void *arg = va_arg(a, void *); va_end(a);
    int video = fd >= 0 && fd < MAX_FD && is_video[fd];
    if (!video) return real(fd, req, arg);

    if (req == UVCIOC_CTRL_QUERY) {
        struct uvc_xu_control_query *q = arg;
        double t = now();
        int is_set = q->query == UVC_SET_CUR;
        pthread_mutex_lock(&lock);
        init_out();
        if (is_set) {
            fprintf(out, "%.6f xu fd=%d unit=%u sel=%u %s size=%u data=", t, fd, q->unit, q->selector, qname(q->query), q->size);
            hex(q->data, q->size);
            fputc('\n', out);
        }
        pthread_mutex_unlock(&lock);
        int r = real(fd, req, arg);
        int e = errno;
        pthread_mutex_lock(&lock);
        if (is_set) {
            fprintf(out, "%.6f xu-ret fd=%d %s ret=%d errno=%d\n", now(), fd, qname(q->query), r, r < 0 ? e : 0);
        } else {
            if (r >= 0 && q->query == UVC_GET_CUR && q->selector == 2) maybe_rewrite_identity(q->data, q->size);
            fprintf(out, "%.6f xu fd=%d unit=%u sel=%u %s size=%u ret=%d errno=%d data=", t, fd, q->unit, q->selector, qname(q->query), q->size, r, r < 0 ? e : 0);
            if (r >= 0) hex(q->data, q->size);
            fputc('\n', out);
        }
        pthread_mutex_unlock(&lock);
        errno = e;
        return r;
    }

    int r = real(fd, req, arg);
    int e = errno;
    pthread_mutex_lock(&lock);
    init_out();
    fprintf(out, "%.6f ioctl fd=%d req=0x%08lx ret=%d errno=%d\n", now(), fd, req, r, r < 0 ? e : 0);
    pthread_mutex_unlock(&lock);
    errno = e;
    return r;
}
