#define _DEFAULT_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <time.h>
#include <sys/file.h>
static volatile uint32_t *r;
static void barrier(void){__sync_synchronize();}
static int wait_idle(void){for(int i=0;i<1000;i++){barrier();if(!(r[5]&1))return 0;usleep(1000);}fprintf(stderr,"FPGA configuration timed out (RF clock stopped?)\n");return -1;}
static int commit(void){barrier();r[4]=1;barrier();return wait_idle();}
// IIO reports integer-rounded clocks; retain the nominal kHz rate used to
// program the hardware, rather than displaying nanosecond rounding artifacts.
static unsigned long hardware_sample_rate(void){
 for(int i=0;i<32;i++){
  char path[160],name[64];snprintf(path,sizeof path,"/sys/bus/iio/devices/iio:device%d/name",i);
  FILE *f=fopen(path,"r");if(!f)continue;int got=fscanf(f,"%63s",name);fclose(f);if(got!=1||strcmp(name,"ad9361-phy"))continue;
  snprintf(path,sizeof path,"/sys/bus/iio/devices/iio:device%d/in_voltage_sampling_frequency",i);
  f=fopen(path,"r");if(!f)return 0;unsigned long rate=0;if(fscanf(f,"%lu",&rate)!=1)rate=0;fclose(f);return ((rate+500)/1000)*1000;
 }return 0;
}
int main(int argc,char **argv){
 if(argc!=2 || (strcmp(argv[1],"status")&&strcmp(argv[1],"apply")&&strcmp(argv[1],"mute"))){fprintf(stderr,"usage: rtsctl status|apply|mute\n");return 2;}
 int lock=open("/tmp/radar-control.lock",O_CREAT|O_RDWR,0600);if(lock<0||flock(lock,LOCK_EX)){perror("control lock");return 1;}
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0){perror("/dev/mem");return 1;}
 r=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x43c00000);if(r==MAP_FAILED){perror("mmap");return 1;}
 if(r[0]!=0x52545331){fprintf(stderr,"Radar FPGA signature missing\n");return 1;}
 if(!strcmp(argv[1],"apply")){
   uint32_t mask,d[4],f[4],g[4];
   if(scanf("%u",&mask)!=1 || mask>15)return 2;
   for(int t=0;t<4;t++)if(scanf("%u %u %u",&d[t],&f[t],&g[t])!=3 || d[t]>2047 || g[t]>32767)return 2;
   if(wait_idle())return 1;
   for(int t=0;t<4;t++){r[16+4*t]=d[t];r[17+4*t]=f[t];r[18+4*t]=g[t];}
   r[8]=mask;if(commit())return 1;
 }else if(!strcmp(argv[1],"mute")){if(wait_idle())return 1;r[8]=0;if(commit())return 1;}
 printf("{\"signature\":\"RTS1\",\"version\":%u,\"sample_rate_hz\":%lu,\"busy\":%s,\"clipped\":%s,\"mask\":%u,\"targets\":[",r[1],hardware_sample_rate(),(r[5]&1)?"true":"false",r[6]?"true":"false",r[8]);
 for(int t=0;t<4;t++)printf("%s{\"delay_samples\":%u,\"phase_increment\":%d,\"gain_q15\":%u}",t?",":"",r[16+4*t],(int32_t)r[17+4*t],r[18+4*t]);
 printf("]}\n");munmap((void*)r,4096);close(fd);return 0;
}
