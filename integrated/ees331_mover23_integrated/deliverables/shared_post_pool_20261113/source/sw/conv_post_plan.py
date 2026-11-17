"""Plan a single adjacent convolution/affine-post pair before loading a graph.

Input commands are the existing 16x32-bit CNN command format. Return one fused
command (kind6/7) or the two untouched stored commands. The caller still plans
graph leases and renumbers dependencies after replacing two template rows.
All addresses here must be absolute AFTER frame/workspace relocation.
No CPU is involved in the per-element stream transfer.
"""

LIMIT=1<<32

def _span(base,length):
    if not 0<=base<LIMIT or length<=0 or base+length>LIMIT:
        raise ValueError('invalid 32-bit address span')
    return base,base+length

def _overlap(a,b):
    return a[0]<b[1] and b[0]<a[1]

def plan_pair(conv,post,*,consumers=1,request_stream=True,virtual_base=0xE0000000):
    c=list(conv);p=list(post)
    if len(c)!=16 or len(p)!=16 or any(not isinstance(v,int) or not 0<=v<LIMIT for v in c+p):
        raise ValueError('commands must contain sixteen uint32 words')
    fallback=lambda reason:{'fused':False,'reason':reason,'commands':[c,p]}
    if not request_stream:return fallback('disabled')
    if consumers!=1:return fallback('multiple_consumers')
    if c[0] not in (0,5) or p[0]!=1:return fallback('unsupported_pair')
    k=3 if c[0]==0 else 1
    ci,w,h,co,st=c[6],c[7],c[8],c[9],c[10];dw=bool(c[11]&1)
    if not (1<=ci<=512 and 1<=co<=512 and k<=w<=65535 and k<=h<=65535 and st in (1,2)):
        raise ValueError('invalid convolution dimensions')
    if dw and (k==1 or co!=ci):return fallback('unsupported_depthwise')
    n=((w-k)//st+1)*((h-k)//st+1)*co
    if p[1]!=c[3] or p[5]!=n or p[6]!=co:return fallback('layout_or_shape_mismatch')
    if c[3]&3 or p[4]&3 or virtual_base&3:raise ValueError('unaligned raw/parameter address')
    x=_span(c[1],w*h*ci);weights=_span(c[2],co*k*k*(1 if dw else ci))
    raw=_span(c[3],n*4);params=_span(p[4],co*20);dest=_span(p[3],n)
    if _overlap(raw,x) or _overlap(raw,weights):raise ValueError('raw convolution output overlaps source')
    if any(_overlap(dest,a) for a in (x,weights,params)):return fallback('live_output_alias')
    virtual=_span(virtual_base,n*4)
    if _overlap(virtual,x) or _overlap(virtual,weights):raise ValueError('virtual producer base overlaps convolution source')
    c[0]=6 if k==3 else 7;c[3]=p[3];c[4]=p[4];c[5]=n;c[12]=virtual_base
    return {'fused':True,'reason':'direct','commands':[c],'elements':n,'saved_intermediate_bytes':n*8}
