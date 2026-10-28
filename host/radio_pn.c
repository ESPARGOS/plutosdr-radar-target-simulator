// Check RX with a PRBS pattern and TX through digital loopback at startup.
// Restore the FPGA test registers afterward and leave TX attenuated.
#define _DEFAULT_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <signal.h>
static volatile sig_atomic_t interrupted;
static void stop_test(int signum){(void)signum;interrupted=1;}
static char phy[256],debug[256];
static int attr(const char *base,const char *name,const char *value){
 char path[512];snprintf(path,sizeof path,"%s/%s",base,name);
 int fd=open(path,O_WRONLY);if(fd<0){perror(path);return -1;}
 size_t n=strlen(value);int ok=write(fd,value,n)==(ssize_t)n;close(fd);return ok?0:-1;
}
static int readattr(const char *base,const char *name,char *value,size_t size){
 char path[512];snprintf(path,sizeof path,"%s/%s",base,name);FILE *f=fopen(path,"r");
 if(!f)return -1;
 int ok=fgets(value,(int)size,f)!=NULL;fclose(f);return ok?0:-1;
}
static int regread(unsigned reg){
 char value[64];snprintf(value,sizeof value,"0x%x",reg);
 if(attr(debug,"direct_reg_access",value)||readattr(debug,"direct_reg_access",value,sizeof value))return -1;
 return (int)strtoul(value,NULL,0);
}
static int regwrite(unsigned reg,unsigned value){char text[64];snprintf(text,sizeof text,"0x%x 0x%x",reg,value);return attr(debug,"direct_reg_access",text);}
int main(int argc,char **argv){
 signal(SIGINT,stop_test);signal(SIGTERM,stop_test);
 unsigned seconds=argc>1?(unsigned)strtoul(argv[1],NULL,10):2;
 if(!seconds||seconds>60){fprintf(stderr,"duration must be 1..60 seconds\n");return 2;}
 for(int i=0;i<16;i++){
  char name[64];snprintf(phy,sizeof phy,"/sys/bus/iio/devices/iio:device%d",i);
  if(!readattr(phy,"name",name,sizeof name)&&!strncmp(name,"ad9361-phy",10)){
   snprintf(debug,sizeof debug,"/sys/kernel/debug/iio/iio:device%d",i);break;
  }
 }
 if(!debug[0]||attr(phy,"out_voltage0_hardwaregain","-60"))return 2;
 printf("Interface delays: RX=0x%02x TX=0x%02x\n",regread(6),regread(7));
 char prbs[64],loop[64];
 if(readattr(debug,"bist_prbs",prbs,sizeof prbs)||readattr(debug,"loopback",loop,sizeof loop))return 2;
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0){perror("/dev/mem");return 2;}
 volatile uint32_t *rx=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x79020000);
 volatile uint32_t *tx=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x79024000);
 if(rx==MAP_FAILED||tx==MAP_FAILED){perror("mmap");close(fd);return 2;}
 unsigned ro[]={0x400,0x440,0x418,0x458},to[]={0x418,0x458,0x414,0x454};uint32_t rs[4],ts[4];
 for(int i=0;i<4;i++){rs[i]=rx[ro[i]/4];ts[i]=tx[to[i]/4];}
 int failed=0;
 for(int mode=0;mode<2;mode++){
  if(attr(debug,"bist_prbs","0")||attr(debug,"loopback",mode?"1":"0")){failed=1;break;}
  rx[0x40/4]=2;rx[0x40/4]=3;tx[0x40/4]=3;
  for(int ch=0;ch<2;ch++){
   rx[(0x400+64*ch)/4]=0x251;rx[(0x418+64*ch)/4]=mode?9<<16:0;
   if(mode){tx[(0x418+64*ch)/4]=9;tx[(0x414+64*ch)/4]=0;}
  }
  tx[0x44/4]=1;
  if((!mode&&attr(debug,"bist_prbs","2"))||attr(phy,"ensm_mode","alert")||attr(phy,"ensm_mode","fdd")){failed=1;break;}
  usleep(100000);
  if(mode){
   int selected=regread(7);if(selected<0){failed=1;break;}
   for(int attempt=0;attempt<5;attempt++){
    rx[0x404/4]=7;rx[0x444/4]=7;usleep(50000);
    printf("TX acquisition %d: status %u %u\n",attempt+1,rx[0x404/4],rx[0x444/4]);
    if(!((rx[0x404/4]|rx[0x444/4])&6))break;
    if(attempt<4){
     if(regwrite(7,selected?0:0xf0)){failed=1;break;}usleep(10000);
     if(regwrite(7,(unsigned)selected)){failed=1;break;}usleep(50000);
    }
   }
  }
  if(failed)break;
  // Sticky checker errors are cleared once, never during the measured interval.
  rx[0x404/4]=7;rx[0x444/4]=7;
  for(unsigned i=0;i<seconds*10 && !interrupted;i++)usleep(100000);
  if(interrupted){failed=1;break;}
  uint32_t a=rx[0x404/4],b=rx[0x444/4],global=rx[0x5c/4];
  printf("%s: status %u %u, global %u, %u seconds\n",mode?"TX loopback":"RX PN",a,b,global,seconds);
  failed|=((a|b)&6)!=0||!(global&1);
 }
 failed|=attr(debug,"bist_prbs",prbs)!=0;failed|=attr(debug,"loopback",loop)!=0;
 for(int i=0;i<4;i++){rx[ro[i]/4]=rs[i];tx[to[i]/4]=ts[i];}
 rx[0x40/4]=2;rx[0x40/4]=3;tx[0x44/4]=1;
 munmap((void*)rx,4096);munmap((void*)tx,4096);close(fd);
 return failed?1:0;
}
