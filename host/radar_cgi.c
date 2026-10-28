/* Pluto-local CGI adapter. The register helper validates and serializes writes. */
#define main rtsctl_main
#include "rtsctl.c"
#undef main
#include <math.h>
#include <sys/file.h>
#include <errno.h>
#include <glob.h>
static void error(int code,const char *message){printf("Status: %d\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n\r\n{\"error\":\"%s\"}\n",code,message);}
static char phy[256];
static int find_phy(void){
 glob_t paths;if(glob("/sys/bus/iio/devices/iio:device*/name",0,NULL,&paths))return -1;
 for(size_t i=0;i<paths.gl_pathc;i++){FILE *f=fopen(paths.gl_pathv[i],"r");char name[64]={0};if(f){if(fgets(name,sizeof name,f)&&!strncmp(name,"ad9361-phy",10)){snprintf(phy,sizeof phy,"%s",paths.gl_pathv[i]);*strrchr(phy,'/')=0;fclose(f);globfree(&paths);return 0;}fclose(f);}}
 globfree(&paths);return -1;
}
static unsigned long long read_phy_value(const char *name){
 char path[320];snprintf(path,sizeof path,"%s/%s",phy,name);
 FILE *f=fopen(path,"r");unsigned long long value=0;
 if(f){if(fscanf(f,"%llu",&value)!=1)value=0;fclose(f);}return value;
}
static int read_phy_text(const char *name,char *value,size_t size){
 char path[320];snprintf(path,sizeof path,"%s/%s",phy,name);FILE *f=fopen(path,"r");if(!f)return -1;
 int ok=fgets(value,size,f)!=NULL;fclose(f);if(!ok)return -1;value[strcspn(value,"\r\n")]=0;return 0;
}
static int write_phy_text(const char *name,const char *value){
 char path[320];snprintf(path,sizeof path,"%s/%s",phy,name);int fd=open(path,O_WRONLY);if(fd<0)return -1;
 size_t n=strlen(value);int ok=write(fd,value,n)==(ssize_t)n;close(fd);return ok?0:-1;
}
static double read_gain(int tx){char v[80];if(read_phy_text(tx?"out_voltage0_hardwaregain":"in_voltage0_hardwaregain",v,sizeof v))return NAN;char *end;double gain=strtod(v,&end);return end!=v?gain:NAN;}
static int write_gain(int tx,double gain){char value[40];snprintf(value,sizeof value,"%.6f",gain);return write_phy_text(tx?"out_voltage0_hardwaregain":"in_voltage0_hardwaregain",value);}
static int gain_limits(int tx,double *lo,double *step,double *hi){char value[128];return read_phy_text(tx?"out_voltage0_hardwaregain_available":"in_voltage0_hardwaregain_available",value,sizeof value)||sscanf(value,"[%lf %lf %lf]",lo,step,hi)!=3||!isfinite(*lo)||!isfinite(*hi)||!isfinite(*step)||*step<=0?-1:0;}
static unsigned long long read_lo(int tx){char path[320];snprintf(path,sizeof path,"%s/out_altvoltage%d_%s_LO_frequency",phy,tx,tx?"TX":"RX");FILE *f=fopen(path,"r");unsigned long long hz=0;if(f){if(fscanf(f,"%llu",&hz)!=1)hz=0;fclose(f);}return hz;}
static int write_lo(int tx,unsigned long long hz){char path[320],value[32];snprintf(path,sizeof path,"%s/out_altvoltage%d_%s_LO_frequency",phy,tx,tx?"TX":"RX");int fd=open(path,O_WRONLY);if(fd<0)return -1;int n=snprintf(value,sizeof value,"%llu\n",hz);int ok=write(fd,value,n)==n;close(fd);return ok?0:-1;}
int main(void){
 const char *method=getenv("REQUEST_METHOD"),*path=getenv("PATH_INFO"),*origin=getenv("HTTP_ORIGIN"),*host=getenv("HTTP_HOST");
 if(!method||!path){error(400,"Missing request information");return 0;}
 int apply=!strcmp(path,"/apply"),mute=!strcmp(path,"/mute"),status=!strcmp(path,"/state"),radio=!strcmp(path,"/radio"),gain=!strcmp(path,"/gain");
 if(!apply&&!mute&&!status&&!radio&&!gain){error(404,"Unknown endpoint");return 0;}
 if(strcmp(method,status?"GET":"POST")){error(405,"Invalid method");return 0;}
 if(!status&&origin){char expected[300];snprintf(expected,sizeof expected,"http://%s",host?host:"");if(strcmp(origin,expected)){error(403,"Cross-origin request rejected");return 0;}}
 if(access("/tmp/radar-loaded",F_OK)){error(503,"Radar FPGA is not ready");return 0;}
 uint32_t mask=0,d[4]={0},f[4]={0},g[4]={0};
 if(apply){
  const char *len=getenv("CONTENT_LENGTH");char *end;long n=len?strtol(len,&end,10):0;
  if(!len||*end||n<=0||n>1024){error(400,"Invalid payload length");return 0;}
  char data[1025];if(fread(data,1,n,stdin)!=(size_t)n){error(400,"Incomplete payload");return 0;}data[n]=0;
  char *p=data;uint32_t values[13];
  for(int i=0;i<13;i++){while(*p==' '||*p=='\n'||*p=='\r'||*p=='\t')p++;if(*p<'0'||*p>'9'){error(400,"Expected unsigned register values");return 0;}errno=0;unsigned long v=strtoul(p,&end,10);if(errno||v>UINT32_MAX){error(400,"Register value out of range");return 0;}values[i]=(uint32_t)v;p=end;}
  while(*p==' '||*p=='\n'||*p=='\r'||*p=='\t')p++;
  if(*p||values[0]>15){error(400,"Invalid target mask or trailing data");return 0;}mask=values[0];
  for(int i=0;i<4;i++){d[i]=values[1+3*i];f[i]=values[2+3*i];g[i]=values[3+3*i];if(d[i]>2047||g[i]>32767||f[i]==0x80000000){error(400,"Target value out of range");return 0;}}
 }
 unsigned long long requested=0;
 if(radio){
  const char *len=getenv("CONTENT_LENGTH");char *end;long n=len?strtol(len,&end,10):0;
  if(!len||*end||n<1||n>16){error(400,"Invalid frequency payload");return 0;}
  char value[17];if(fread(value,1,n,stdin)!=(size_t)n){error(400,"Incomplete frequency");return 0;}value[n]=0;
  for(long i=0;i<n;i++)if(value[i]<'0'||value[i]>'9'){error(400,"Frequency must be integer Hz");return 0;}
  requested=strtoull(value,NULL,10);
  if(requested<325000000ULL||requested>3800000000ULL){error(400,"Carrier must be between 325 and 3800 MHz");return 0;}
 }
 int gain_tx=0;double requested_gain=0;
 if(gain){
  const char *len=getenv("CONTENT_LENGTH");char *end;long n=len?strtol(len,&end,10):0;
  if(!len||*end||n<1||n>48){error(400,"Invalid gain payload");return 0;}
  char value[49],channel[3];int consumed=0;
  if(fread(value,1,n,stdin)!=(size_t)n){error(400,"Incomplete gain payload");return 0;}value[n]=0;
  if(sscanf(value,"%2s %lf %n",channel,&requested_gain,&consumed)!=2||consumed!=n||!isfinite(requested_gain)||(strcmp(channel,"rx")&&strcmp(channel,"tx"))){error(400,"Expected rx or tx and a finite gain in dB");return 0;}
  gain_tx=!strcmp(channel,"tx");
 }
 int lock=open("/tmp/radar-control.lock",O_CREAT|O_RDWR,0600);if(lock<0||flock(lock,LOCK_EX)){error(503,"Control lock unavailable");return 0;}
 int fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0){error(503,"FPGA access unavailable");return 0;}
 r=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x43c00000);if(r==MAP_FAILED||r[0]!=0x52545331){error(503,"Radar FPGA signature missing");return 0;}
 if(wait_idle()){error(503,"FPGA configuration timed out");return 0;}
 if(find_phy()){error(503,"Radio unavailable");return 0;}
 double fs=hardware_sample_rate();if(fs<=0){error(503,"Cannot read sample clock");return 0;}
 unsigned long long frequency=read_lo(0),tx_frequency=read_lo(1);
 if(!frequency||!tx_frequency){error(503,"Cannot read carrier frequency");return 0;}
 if(radio){
  r[8]=0;if(commit()){error(503,"Could not mute targets before tuning");return 0;}
  if(write_lo(0,requested)||write_lo(1,requested)||llabs((long long)read_lo(0)-(long long)requested)>10||read_lo(0)!=read_lo(1)){
   int rx_ok=write_lo(0,frequency),tx_ok=write_lo(1,tx_frequency);
   error(503,rx_ok||tx_ok?"Tuning failed; targets muted; radio requires reconfiguration":"Tuning failed; previous frequency restored; targets muted");return 0;
  }
  frequency=read_lo(0);
 }
 double rx_min,rx_step,rx_max,tx_min,tx_step,tx_max;
 if(gain_limits(0,&rx_min,&rx_step,&rx_max)||gain_limits(1,&tx_min,&tx_step,&tx_max)){error(503,"Cannot read gain limits");return 0;}
 if(gain){
  double lo=gain_tx?tx_min:rx_min,hi=gain_tx?tx_max:rx_max,step=gain_tx?tx_step:rx_step;
  if(requested_gain<lo||requested_gain>hi||fabs((requested_gain-lo)/step-round((requested_gain-lo)/step))>1e-5){error(400,"Gain is outside the supported range or step");return 0;}
  double old=read_gain(gain_tx);char mode[40]="manual";
  if(!isfinite(old)||(!gain_tx&&read_phy_text("in_voltage0_gain_control_mode",mode,sizeof mode))){error(503,"Cannot read current gain");return 0;}
  if((!gain_tx&&write_phy_text("in_voltage0_gain_control_mode","manual"))||write_gain(gain_tx,requested_gain)||!isfinite(read_gain(gain_tx))||fabs(read_gain(gain_tx)-requested_gain)>.001){
   int restored=write_gain(gain_tx,old);if(!gain_tx)restored|=write_phy_text("in_voltage0_gain_control_mode",mode);
   error(503,restored?"Gain update failed; check radio settings":"Gain update failed; previous setting restored");return 0;
  }
 }
 double rx_gain=read_gain(0),tx_gain=read_gain(1);
 if(!isfinite(rx_gain)||!isfinite(tx_gain)){error(503,"Cannot read radio gains");return 0;}
 if(apply){for(int i=0;i<4;i++){r[16+4*i]=d[i];r[17+4*i]=f[i];r[18+4*i]=g[i];}r[8]=mask;}
 if(mute)r[8]=0;
 if((apply||mute)&&commit()){error(503,"FPGA configuration timed out");return 0;}
 /* Measured RF latency for the qualified two-cycle, 160 MHz / 20 MHz profile.
    Other profiles deliberately report unknown, rather than a false total range. */
 const char *latency=(r[1]==0x00010010 && fabs(fs-160000000)<100 &&
  read_phy_value("in_voltage_rf_bandwidth")==20000000 &&
  read_phy_value("out_voltage_rf_bandwidth")==20000000)?"0.325":"null";
 printf("Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n{\"mode\":\"hardware\",\"connected\":true,\"error\":null,\"pluto\":\"on-device\",\"sample_rate_hz\":%.0f,\"frequency_hz\":%llu,\"max_targets\":4,\"max_delay_us\":%.9f,\"delay_step_us\":%.12f,\"doppler_step_hz\":%.12f,\"rx_bandwidth_hz\":%llu,\"tx_bandwidth_hz\":%llu,\"rx_gain_db\":%.6f,\"tx_gain_db\":%.6f,\"rx_gain_min_db\":%.6f,\"rx_gain_max_db\":%.6f,\"rx_gain_step_db\":%.6f,\"tx_gain_min_db\":%.6f,\"tx_gain_max_db\":%.6f,\"tx_gain_step_db\":%.6f,\"hardware_latency_us\":%s,\"latency_calibrated\":false,\"clipped\":%s,\"targets\":[",fs,frequency,2047e6/fs,1e6/fs,fs/4294967296.0,read_phy_value("in_voltage_rf_bandwidth"),read_phy_value("out_voltage_rf_bandwidth"),rx_gain,tx_gain,rx_min,rx_max,rx_step,tx_min,tx_max,tx_step,latency,r[6]?"true":"false");
 int emitted=0;
 for(int i=0;i<4;i++){if(!r[18+4*i]&&!(r[8]&(1<<i)))continue;double gain=r[18+4*i]?20*log10(r[18+4*i]/32768.0):-90;printf("%s{\"id\":%d,\"enabled\":%s,\"delay_us\":%.8f,\"doppler_hz\":%.9f,\"gain_db\":%.5f}",emitted++?",":"",i+1,r[8]&(1<<i)?"true":"false",r[16+4*i]*1e6/fs,(int32_t)r[17+4*i]*(fs/4294967296.0),fmax(-90,gain));}
 printf("]}\n");munmap((void*)r,4096);close(fd);close(lock);return 0;
}
