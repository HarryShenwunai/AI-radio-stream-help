"""Dependency-free measured affine/similarity residuals in source canvas pixels.

No artistic threshold is implied. Fitting uses every supplied point unless the
caller explicitly selects a separate, reported texture-supported fit subset.
"""
from __future__ import annotations
import math


def points(values):
    if not isinstance(values,(list,tuple)) or len(values)<3:
        raise ValueError('at least three actual points required')
    result=[]
    for row in values:
        if not isinstance(row,(list,tuple)) or len(row)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in row):
            raise ValueError('finite numeric 2D points required')
        result.append(tuple(float(v)for v in row))
    return result


def quantiles(values,percentiles=(0,50,90,95,99,100)):
    if not values or any(not math.isfinite(v)for v in values):
        raise ValueError('finite nonempty measurements required')
    ordered=sorted(values);out={}
    for q in percentiles:
        if not 0<=q<=100:raise ValueError('percentile out of range')
        x=(len(ordered)-1)*q/100;i=math.floor(x);j=math.ceil(x)
        out[str(q)]=ordered[i]+(ordered[j]-ordered[i])*(x-i)
    return out


def fit_transform(reference,target,kind='affine',fit_indices=None):
    ref,dst=points(reference),points(target)
    if len(ref)!=len(dst):raise ValueError('actual topology size changed')
    ids=list(range(len(ref)))if fit_indices is None else list(fit_indices)
    if len(ids)<3 or len(set(ids))!=len(ids) or any(isinstance(i,bool)or not isinstance(i,int)or not 0<=i<len(ref)for i in ids):
        raise ValueError('at least three distinct actual fit indices required')
    n=len(ids);mx=math.fsum(ref[i][0]for i in ids)/n;my=math.fsum(ref[i][1]for i in ids)/n;mu=math.fsum(dst[i][0]for i in ids)/n;mv=math.fsum(dst[i][1]for i in ids)/n
    centered=[(ref[i][0]-mx,ref[i][1]-my,dst[i][0]-mu,dst[i][1]-mv)for i in ids]
    xx=math.fsum(x*x for x,y,u,v in centered);xy=math.fsum(x*y for x,y,u,v in centered);yy=math.fsum(y*y for x,y,u,v in centered)
    det=xx*yy-xy*xy
    if not math.isfinite(det)or det<=1e-12*(xx+yy)**2:raise ValueError('reference points are degenerate or ill-conditioned')
    xu=math.fsum(x*u for x,y,u,v in centered);yu=math.fsum(y*u for x,y,u,v in centered);xv=math.fsum(x*v for x,y,u,v in centered);yv=math.fsum(y*v for x,y,u,v in centered)
    if kind=='affine':
        a=(xu*yy-yu*xy)/det;b=(yu*xx-xu*xy)/det;c=(xv*yy-yv*xy)/det;d=(yv*xx-xv*xy)/det
    elif kind=='similarity':
        a=d=(xu+yv)/(xx+yy);c=(xv-yu)/(xx+yy);b=-c
    else:raise ValueError('unknown transform class')
    tx=mu-a*mx-b*my;ty=mv-c*mx-d*my
    residual_xy=[(a*x+b*y+tx-u,c*x+d*y+ty-v)for(x,y),(u,v)in zip(ref,dst)];errors=[math.hypot(*v)for v in residual_xy]
    if not all(math.isfinite(v)for v in errors):raise ValueError('nonfinite fitted result')
    frobenius2=a*a+b*b+c*c+d*d;det_a=a*d-b*c;disc=math.sqrt(max(0,frobenius2*frobenius2-4*det_a*det_a));lo=math.sqrt(max(0,(frobenius2-disc)/2));hi=math.sqrt(max(0,(frobenius2+disc)/2))
    return {'kind':kind,'matrix_3x2':[[a,c],[b,d],[tx,ty]],'fit_vertex_count':len(ids),'residual_xy_source_px':residual_xy,'residual_source_px':errors,
        'max_source_px':max(errors),'rms_source_px':math.sqrt(math.fsum(v*v for v in errors)/len(errors)),'worst_vertex_index':max(range(len(errors)),key=errors.__getitem__),
        'singular_values':[lo,hi],'determinant':det_a,'similarity_scale':math.hypot(a,c)if kind=='similarity'else None,'nondegenerate':lo>0}
