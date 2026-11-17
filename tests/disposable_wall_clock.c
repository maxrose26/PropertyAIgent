#define _GNU_SOURCE
#include <time.h>
#include <sys/time.h>
#include <dlfcn.h>
int clock_gettime(clockid_t id, struct timespec *v) {
 static int (*real)(clockid_t,struct timespec*); if(!real)real=dlsym(RTLD_NEXT,"clock_gettime");
 int r=real(id,v); if(!r && id==CLOCK_REALTIME)v->tv_sec-=7200; return r;
}
int gettimeofday(struct timeval *v, void *z) {
 static int (*real)(struct timeval*,void*); if(!real)real=dlsym(RTLD_NEXT,"gettimeofday");
 int r=real(v,z); if(!r && v)v->tv_sec-=7200; return r;
}
time_t time(time_t *v) { static time_t (*real)(time_t*);if(!real)real=dlsym(RTLD_NEXT,"time");time_t r=real(0)-7200;if(v)*v=r;return r; }
