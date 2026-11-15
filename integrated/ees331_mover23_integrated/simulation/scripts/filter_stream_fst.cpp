// Select real FST signals and time ranges without fabricating transitions.
#include "fstapi.h"
#include <fstream>
#include <iostream>
#include <set>
#include <string>
#include <vector>
#include <algorithm>
struct Context {fstWriterContext* w;std::vector<fstHandle> map;uint64_t begin,end,now;};
static void change(void* user,uint64_t time,fstHandle h,const unsigned char* value){
    auto& c=*static_cast<Context*>(user);
    if(time>c.end || h>=c.map.size() || !c.map[h])return;
    time=std::max(time,c.begin);
    if(time!=c.now){fstWriterEmitTimeChange(c.w,time);c.now=time;}
    fstWriterEmitValueChange(c.w,c.map[h],value);
}
int main(int argc,char**argv){
    if(argc!=6)return 2;
    std::ifstream names(argv[3]);std::set<std::string> wanted;std::string name;
    while(std::getline(names,name)){if(!name.empty() && name.back()=='\r')name.pop_back();wanted.insert(name);}
    auto* r=fstReaderOpen(argv[1]);if(!r)return 3;
    Context c{fstWriterCreate(argv[2],1),std::vector<fstHandle>(fstReaderGetMaxHandle(r)+1),std::stoull(argv[4]),std::stoull(argv[5]),std::stoull(argv[4])};
    fstWriterSetTimescale(c.w,fstReaderGetTimescale(r));fstWriterSetScope(c.w,FST_ST_VCD_MODULE,"stream_top",nullptr);
    std::vector<std::string> scope;std::set<std::string> found;
    while(auto* h=fstReaderIterateHier(r)){
        if(h->htyp==FST_HT_SCOPE)scope.emplace_back(h->u.scope.name);
        else if(h->htyp==FST_HT_UPSCOPE)scope.pop_back();
        else if(h->htyp==FST_HT_VAR && scope==std::vector<std::string>{"tb_soc_stream","dut"}){
            std::string full=h->u.var.name,base=full.substr(0,full.find(' '));
            if(!wanted.count(base))continue;
            auto handle=h->u.var.handle;
            auto out=fstWriterCreateVar(c.w,FST_VT_VCD_WIRE,FST_VD_IMPLICIT,h->u.var.length,full.c_str(),c.map[handle]);
            if(!c.map[handle])c.map[handle]=out;
            fstReaderSetFacProcessMask(r,handle);found.insert(base);
        }
    }
    if(found!=wanted){for(auto& n:wanted)if(!found.count(n))std::cerr<<"missing "<<n<<"\n";return 4;}
    fstWriterSetUpscope(c.w);fstWriterEmitTimeChange(c.w,c.begin);
    fstReaderSetLimitTimeRange(r,c.begin,c.end);fstReaderIterBlocks(r,change,&c,nullptr);
    fstWriterEmitTimeChange(c.w,c.end);fstWriterClose(c.w);fstReaderClose(r);
    std::cout<<"PASS filtered "<<found.size()<<" signals, ps "<<c.begin<<".."<<c.end<<"\n";
}
